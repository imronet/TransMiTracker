"""Manual, offline route tracking. Candidate continuity is not operational identity."""

import argparse
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from transmitracker.catalog import CatalogError
from transmitracker.catalog.queries import Catalog
from transmitracker.diagnostics import project_path
from transmitracker.reconstruction.geometry import MeasuredShape, select_projection
from transmitracker.reconstruction.io import read_saved_capture
from transmitracker.reconstruction.models import Parameters, canonical
from transmitracker.research.local_pilot import pilot_path, write_json
from transmitracker.research.temporal import distance_m

VERSION = "route-tracker-experimental-0.1.0"


class RouteGeometry:
    """One geometry per distinct shape, with every associated pattern retained."""

    def __init__(self, catalog, route_id, parameters):
        self.parameters = parameters
        self.shapes = {}
        self.patterns = defaultdict(list)
        for row in catalog.connection.execute(
            "SELECT pattern_id,shape_id FROM patterns WHERE route_id=? ORDER BY pattern_id",
            (route_id,),
        ):
            self.patterns[row["shape_id"]].append(row["pattern_id"])
        for shape_id in self.patterns:
            points = catalog.connection.execute(
                "SELECT latitude,longitude FROM shape_points WHERE shape_id=? ORDER BY sequence",
                (shape_id,),
            ).fetchall()
            if len(points) >= 2:
                self.shapes[shape_id] = SimpleNamespace(
                    shape=MeasuredShape([tuple(p) for p in points]), stops=()
                )

    def project(self, observation):
        choices, unresolved = [], False
        for shape_id, geometry in sorted(self.shapes.items()):
            projection, reason = select_projection(geometry, observation, self.parameters)
            choices.append(
                {
                    "shape_id": shape_id,
                    "pattern_ids": self.patterns[shape_id],
                    "projection": asdict(projection) if projection else None,
                    "reason": reason,
                }
            )
            unresolved |= projection is None and reason != "off_shape_or_missing_geometry"
        valid = [c for c in choices if c["projection"] is not None]
        if unresolved or len(valid) > 1:
            return choices, None, "ambiguous_geometry"
        if not valid:
            return choices, None, "off_shape" if self.shapes else "no_geometry"
        return choices, valid[0], None


def load_session(directory, catalog_hash):
    directory = Path(directory).resolve()
    manifest = directory / "session.json"
    payload = manifest.read_bytes()
    session = json.loads(payload)
    names = session["captures"]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate capture entries in session manifest")
    snapshots = []
    for name in names:
        record = (directory / name).resolve()
        if not record.is_relative_to(directory):
            raise ValueError("Capture path escapes session")
        snapshots.append(read_saved_capture(record, catalog_hash))
    if len({s.origin for s in snapshots}) > 1:
        raise ValueError("Real and synthetic evidence must remain separate")
    return snapshots, hashlib.sha256(payload).hexdigest()


def _fix(snapshot, frame, ordinal, observation):
    return {
        "snapshot_index": frame,
        "observation_ordinal": ordinal,
        "snapshot_id": snapshot.snapshot_id,
        "payload_sha256": snapshot.payload_sha256,
        "received_at": snapshot.received_at,
        "feed_as_of": snapshot.feed_as_of,
        "observation": asdict(observation),
    }


def _state(fix):
    r = fix["observation"]
    return (r["route_id"], r["reported_at"], r["latitude"], r["longitude"])


def track(snapshots, route_id, *, geometry=None, parameters=None):
    """Inspect full snapshots for boundaries before selecting the route's movements.

    GPS order is increasing within each reception epoch/segment. A regressing
    GPS clock cuts the epoch; sorting never conceals that boundary.
    """
    if not isinstance(route_id, str) or not route_id:
        raise ValueError("An exact route_id string is required")
    parameters = parameters or Parameters(max_gap_s=300)
    originals, cohort, frames = [], set(), []
    for index, snapshot in enumerate(snapshots):
        frame = defaultdict(list)
        for ordinal, observation in enumerate(snapshot.observations):
            fix = _fix(snapshot, index, ordinal, observation)
            frame[(observation.source, observation.vehicle_id)].append(fix)
            if observation.route_id == route_id:
                originals.append(fix)
                if observation.vehicle_id:
                    cohort.add((observation.source, observation.vehicle_id))
        frames.append(frame)
    vehicles = []
    for source, vehicle in sorted(cohort):
        key = (source, vehicle)
        sightings = [f for frame in frames for f in frame.get(key, [])]
        target = [f for f in sightings if f["observation"]["route_id"] == route_id]
        conflicts = defaultdict(set)
        for f in sightings:
            r = f["observation"]
            if r["reported_at"] is not None:
                conflicts[r["reported_at"]].add((r["latitude"], r["longitude"]))
        bad_times = {t for t, v in conflicts.items() if len(v) > 1}
        incidents, segments, changes, seen_states = [], [], Counter(), set()
        current, pending, last_time, prior_aux, duplicates = [], "session_start", None, None, 0

        def close(reason, interrupted=True, segments=segments):
            nonlocal current, pending
            if current:
                first, last = current[0], current[-1]
                distances = [
                    distance_m(
                        (a["observation"]["latitude"], a["observation"]["longitude"]),
                        (b["observation"]["latitude"], b["observation"]["longitude"]),
                    )
                    for a, b in zip(current, current[1:], strict=False)
                ]
                progress = None
                if all(f["selected_geometry"] is not None for f in current):
                    progress = (
                        last["selected_geometry"]["projection"]["progress_m"]
                        - first["selected_geometry"]["projection"]["progress_m"]
                    )
                sampled = sum(distances)
                activity = (
                    "descartado"
                    if len(current) < 2
                    else "movimiento_candidato"
                    if (
                        progress > parameters.backtrack_tolerance_m
                        if progress is not None
                        else sampled > parameters.gps_error_m
                    )
                    else "estacionario"
                )
                state = "interrumpido" if interrupted and len(current) >= 2 else activity
                segments.append(
                    {
                        "segment_index": len(segments),
                        "state": state,
                        "activity_candidate": activity,
                        "start_reason": pending,
                        "end_reason": reason,
                        "first_gps_timestamp": first["observation"]["reported_at"],
                        "last_gps_timestamp": last["observation"]["reported_at"],
                        "fixes": current,
                        "position_changes": sum(d > 0 for d in distances),
                        "sampled_distance_m": sampled,
                        "geometric_progress_m": progress,
                        "pattern_ambiguous": any(
                            f["selected_geometry"] is not None
                            and len(f["selected_geometry"]["pattern_ids"]) > 1
                            for f in current
                        ),
                    }
                )
            current, pending = [], reason

        def incident(reason, fixes, incidents=incidents):
            incidents.append(
                {
                    "reason": reason,
                    "snapshot_indices": [f["snapshot_index"] for f in fixes],
                    "observation_ids": [f["observation"]["observation_id"] for f in fixes],
                }
            )

        def discard(fix, reason, state="descartado", segments=segments):
            close(reason)
            incident(reason, [fix])
            segments.append(
                {
                    "segment_index": len(segments),
                    "state": state,
                    "activity_candidate": state,
                    "start_reason": reason,
                    "end_reason": reason,
                    "first_gps_timestamp": fix["observation"]["reported_at"],
                    "last_gps_timestamp": fix["observation"]["reported_at"],
                    "fixes": [fix],
                    "position_changes": 0,
                    "sampled_distance_m": 0,
                    "geometric_progress_m": None,
                    "pattern_ambiguous": state == "ambiguo",
                }
            )

        for index, (snapshot, frame) in enumerate(zip(snapshots, frames, strict=True)):
            if snapshot.source != source:
                continue
            observed = frame.get(key, [])
            if not observed:
                if current and snapshot.complete:
                    last_fix = current[-1]
                    close("missing_from_complete_snapshot")
                    incidents.append(
                        {
                            "reason": "missing_from_complete_snapshot",
                            "snapshot_indices": [index],
                            "observation_ids": [last_fix["observation"]["observation_id"]],
                        }
                    )
                continue
            if len({_state(f) for f in observed}) > 1:
                close("conflicting_vehicle_in_snapshot")
                incident("conflicting_vehicle_in_snapshot", observed)
                continue
            f = dict(observed[0], shape_candidates=[], selected_geometry=None)
            r = f["observation"]
            if prior_aux is not None:
                for field in (
                    "trip_id",
                    "start_time",
                    "start_date",
                    "stop_id",
                    "current_stop_sequence",
                ):
                    changes[field] += r[field] != prior_aux[field]
            prior_aux = r
            if r["route_id"] != route_id:
                close("route_change")
                incident("route_change", observed)
                continue
            if r["reported_at"] is None or r["latitude"] is None or r["longitude"] is None:
                discard(f, "missing_gps_fields")
                continue
            if (
                not all(math.isfinite(r[k]) for k in ("reported_at", "latitude", "longitude"))
                or not -90 <= r["latitude"] <= 90
                or not -180 <= r["longitude"] <= 180
            ):
                discard(f, "invalid_gps_fields")
                continue
            ts = r["reported_at"]
            if ts in bad_times:
                discard(f, "conflicting_positions_at_same_gps_time")
                continue
            if f["received_at"] is None:
                discard(f, "unverified_reception_time")
                continue
            age = f["received_at"] - ts
            if age > parameters.max_age_s or age < -parameters.future_tolerance_s:
                discard(f, "stale_or_future_gps")
                continue
            if last_time is not None and ts < last_time:
                close("gps_time_regression")
                incident("gps_time_regression", observed)
            last_time = ts
            if _state(f) in seen_states:
                duplicates += len(observed)
                incident("repeated_gps_state", observed)
                continue
            seen_states.add(_state(f))
            duplicates += len(observed) - 1
            if current:
                previous = current[-1]["observation"]
                dt = ts - previous["reported_at"]
                if dt > parameters.max_gap_s:
                    close("gps_gap")
                    incident("gps_gap", observed)
                elif (
                    distance_m(
                        (previous["latitude"], previous["longitude"]),
                        (r["latitude"], r["longitude"]),
                    )
                    / dt
                    > parameters.max_speed_mps
                ):
                    discard(f, "implausible_spatial_jump")
                    continue
            if geometry is not None:
                f["shape_candidates"], f["selected_geometry"], error = geometry.project(
                    SimpleNamespace(**r)
                )
                if error not in (None, "no_geometry"):
                    discard(f, error, "ambiguo" if error == "ambiguous_geometry" else "descartado")
                    continue
                if current and current[-1]["selected_geometry"] and f["selected_geometry"]:
                    a, b = current[-1]["selected_geometry"], f["selected_geometry"]
                    dt = ts - current[-1]["observation"]["reported_at"]
                    dp = b["projection"]["progress_m"] - a["projection"]["progress_m"]
                    reason = (
                        "shape_candidate_changed"
                        if a["shape_id"] != b["shape_id"]
                        else "geometry_backtrack"
                        if dp < -parameters.backtrack_tolerance_m
                        else "geometry_progress_jump"
                        if dp > parameters.max_speed_mps * dt + parameters.gps_error_m
                        else None
                    )
                    if reason:
                        close(reason)
                        incident(reason, observed)
            current.append(f)
        close("session_end", interrupted=False)
        vehicles.append(
            {
                "source": source,
                "vehicle_id": vehicle,
                "original_route_observations": len(target),
                "distinct_published_gps_times": len(
                    {
                        f["observation"]["reported_at"]
                        for f in target
                        if f["observation"]["reported_at"] is not None
                    }
                ),
                "duplicates_removed_from_movement": duplicates,
                "temporal_exact_duplicate_sightings": sum(
                    n - 1
                    for n in Counter(
                        _state(f) for f in target if f["observation"]["reported_at"] is not None
                    ).values()
                ),
                "auxiliary_changes": dict(changes),
                "incidents": incidents,
                "all_source_vehicle_sightings": sightings,
                "segments": segments,
            }
        )
    return {
        "algorithm": VERSION,
        "route_id": route_id,
        "parameters": asdict(parameters),
        "vehicle_candidates": len(vehicles),
        "original_route_observations": len(originals),
        "distinct_published_gps_times": sum(v["distinct_published_gps_times"] for v in vehicles),
        "observations_without_vehicle_id": sum(
            not f["observation"]["vehicle_id"] for f in originals
        ),
        "original_route_sightings": originals,
        "vehicles": vehicles,
        "segment_states": dict(Counter(s["state"] for v in vehicles for s in v["segments"])),
        "network_requests": 0,
        "operationally_verified": False,
        "arrivals_boarding_travel_durations_inferred": False,
    }


def run(directory, route_id, catalog_path=None):
    catalog = Catalog(catalog_path) if catalog_path is not None else None
    try:
        info = catalog.info() if catalog else None
        snapshots, session_hash = load_session(
            directory, info["sha256"] if info else "not_selected"
        )
        geometry = RouteGeometry(catalog, route_id, Parameters(max_gap_s=300)) if catalog else None
        report = track(snapshots, route_id, geometry=geometry)
        report.update(
            session_manifest_sha256=session_hash,
            origins=sorted({s.origin for s in snapshots}),
            catalog=info,
            geometry_available=bool(geometry and geometry.shapes),
            code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            snapshot_provenance=[
                {k: v for k, v in asdict(s).items() if k != "observations"} for s in snapshots
            ],
        )
        report["catalog_route_found"] = bool(
            catalog
            and catalog.connection.execute(
                "SELECT 1 FROM routes WHERE route_id=?", (route_id,)
            ).fetchone()
        )
        report["geometry_status"] = (
            "not_requested"
            if catalog is None
            else "route_not_in_catalog"
            if not report["catalog_route_found"]
            else "usable_shape_candidates"
            if report["geometry_available"]
            else "patterns_without_usable_shape"
        )
        return report
    finally:
        if catalog:
            catalog.close()


def _cli_problem(error, stage):
    """Fixed diagnostics only: exception text can contain private feed data."""
    if isinstance(error, FileExistsError):
        return "OUTPUT_EXISTS", "La salida ya existe; elija un archivo nuevo."
    if stage == "output":
        return "OUTPUT_PATH", "La salida debe ser un archivo nuevo dentro de data/pilots."
    if stage == "write":
        return "OUTPUT_WRITE", "No se pudo escribir el reporte privado; revise permisos y espacio."
    if isinstance(error, (CatalogError, sqlite3.Error)):
        return (
            "CATALOG",
            "No se pudo abrir o consultar el catalogo local; revise archivo y esquema.",
        )
    if isinstance(error, FileNotFoundError):
        return "INPUT_MISSING", "Falta un archivo de la sesion; revise manifiesto, registros y PB."
    if isinstance(error, json.JSONDecodeError):
        return "INPUT_JSON", "El manifiesto o un registro no contiene JSON valido."
    if isinstance(error, UnicodeError):
        return "INPUT_ENCODING", "El manifiesto o un registro no tiene una codificacion valida."
    if isinstance(error, OSError):
        return "INPUT_READ", "No se pudo leer la entrada local; revise acceso y permisos."
    if isinstance(error, ValueError) and str(error) == "Saved capture hash mismatch":
        return (
            "INPUT_INTEGRITY",
            "El hash del PB no coincide con su registro; conserve los originales.",
        )
    return "INPUT_INVALID", "Estructura, campos o contenido de la sesion incompatibles."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session")
    parser.add_argument("--route", required=True, help="Exact published route_id")
    parser.add_argument("--catalog", help="Optional local read-only SQLite catalog")
    parser.add_argument("--output", required=True, help="New private JSON under data/pilots")
    args = parser.parse_args(argv)
    stage = "output"
    try:
        output = pilot_path(project_path(args.output))
        if output.exists():
            raise FileExistsError("Output already exists")
        stage = "input"
        report = run(
            project_path(args.session),
            args.route,
            project_path(args.catalog) if args.catalog else None,
        )
        stage = "write"
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, json.loads(canonical(report)))
        print(
            "Rastreo offline experimental: "
            + canonical(
                {
                    "vehiculos_candidatos": report["vehicle_candidates"],
                    "observaciones": report["original_route_observations"],
                    "estados_segmentos": report["segment_states"],
                    "geometria_disponible": report["geometry_available"],
                    "red": 0,
                    "identidad_operativa_verificada": False,
                }
            )
        )
        return 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        code, message = _cli_problem(error, stage)
        parser.exit(2, f"Error offline [{code}]: {message} Sin adquisicion ni reintento.\n")


if __name__ == "__main__":
    raise SystemExit(main())
