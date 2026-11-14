"""Offline OD hypotheses over existing tracker segments, never validated operation."""

import argparse
import hashlib
import json
import math
import sqlite3
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

from transmitracker.catalog.queries import Catalog
from transmitracker.diagnostics import project_path
from transmitracker.profiles.models import Leg
from transmitracker.reconstruction import implementation_hash
from transmitracker.reconstruction.events import crossing_events, measure
from transmitracker.reconstruction.geometry import GeometryCatalog, select_projection
from transmitracker.reconstruction.models import (
    CandidateIdentity,
    Confidence,
    EventKind,
    NormalizedObservation,
    OriginalObservation,
    Parameters,
    TrajectorySegment,
    canonical,
    digest,
)
from transmitracker.research.local_pilot import pilot_path, write_json
from transmitracker.research.temporal import distance_m
from transmitracker.viewer.data import prepare

VERSION = "od-candidate-offline-0.1.0"


class InputError(ValueError):
    """Only fixed non-identifying diagnostic codes may leave the CLI."""


def select_leg(
    catalog, route, pattern, origin, destination, origin_sequence=None, destination_sequence=None
):
    patterns = catalog.structural_patterns(route)
    if pattern is None:
        if len(patterns) != 1:
            raise InputError("PATTERN_REQUIRED")
        pattern = patterns[0]["pattern_id"]
    match = next((p for p in patterns if p["pattern_id"] == pattern), None)
    if match is None:
        raise InputError("PATTERN_ROUTE_MISMATCH")

    def occurrence(stop, sequence):
        rows = catalog.connection.execute(
            "SELECT sequence FROM pattern_stops WHERE pattern_id=? AND stop_id=? ORDER BY sequence",
            (pattern, stop),
        ).fetchall()
        if not rows:
            raise InputError("STOP_NOT_IN_PATTERN")
        if sequence is None:
            if len(rows) != 1:
                raise InputError("STOP_OCCURRENCE_REQUIRED")
            return rows[0][0]
        if type(sequence) is not int or not any(r[0] == sequence for r in rows):
            raise InputError("STOP_NOT_IN_PATTERN")
        return sequence

    a, b = occurrence(origin, origin_sequence), occurrence(destination, destination_sequence)
    if b <= a:
        raise InputError("DESTINATION_NOT_DOWNSTREAM")
    leg = Leg(origin, route, pattern, match["direction_id"], a, destination, b)
    catalog.validate_leg_structure(leg)
    return leg


def pattern_geometry(catalog, leg, parameters):
    """Reuse 3A anchors, requiring agreement between static templates of one pattern.

    A static template is not a match to a published realtime trip or service.
    Pattern signatures do not include shape_distance, so check its variants.
    """
    variants = {}
    for row in catalog.connection.execute(
        "SELECT s.sequence,s.shape_distance FROM trips t JOIN stop_times s ON s.trip_pk=t.trip_pk WHERE t.pattern_id=? GROUP BY s.sequence,s.shape_distance",
        (leg.pattern_id,),
    ):
        variants.setdefault(row["sequence"], set()).add(row["shape_distance"])
    if any(len(values) > 1 for values in variants.values()):
        return None, None, "pattern_anchor_template_variants"
    template = catalog.connection.execute(
        "SELECT trip_id FROM trips WHERE pattern_id=? ORDER BY trip_id LIMIT 1",
        (leg.pattern_id,),
    ).fetchone()
    geometry = GeometryCatalog(catalog, parameters).load(template[0]) if template else None
    if geometry is None:
        return None, None, "pattern_geometry_unavailable"
    if geometry.route_id != leg.route_id or geometry.pattern_id != leg.pattern_id:
        return None, template[0], "pattern_geometry_incompatible"
    return geometry, template[0], None


def _result(segment):
    return {
        "tracker_segment_index": segment["segment_index"],
        "tracker_state": segment["state"],
        "tracker_start_reason": segment["start_reason"],
        "tracker_end_reason": segment["end_reason"],
        "status": "indeterminate",
        "reasons": [],
        "crossings": [],
        "duration": None,
        "observations": [],
        "auxiliary_changes": {},
        "operationally_validated": False,
    }


def evaluate_segment(raw, source, vehicle, leg, geometry, parameters, report_hash):
    """Reject an unusable segment as a whole; never bridge or resurrect tracker cuts."""
    result = _result(raw)
    fixes = raw["fixes"]
    auxiliary = ("trip_id", "start_time", "start_date", "stop_id", "current_stop_sequence")
    result["auxiliary_changes"] = {
        key: sum(
            a["observation"][key] != b["observation"][key]
            for a, b in zip(fixes, fixes[1:], strict=False)
        )
        for key in auxiliary
    }
    result["original_support"] = fixes
    if raw["state"] in ("ambiguo", "descartado"):
        result["reasons"] = ["tracker_segment_" + raw["state"]]
        return result
    if geometry is None:
        result["reasons"] = ["geometry_not_evaluable"]
        return result
    anchors = [
        s
        for s in geometry.stops
        if (s.stop_id, s.sequence)
        in (
            (leg.origin_stop_id, leg.origin_sequence),
            (leg.destination_stop_id, leg.destination_sequence),
        )
    ]
    if len(anchors) != 2 or any(s.progress_m is None for s in anchors):
        result["reasons"] = sorted(
            {"endpoint_anchor_unresolved"} | {s.reason for s in anchors if s.progress_m is None}
        )
        return result
    if anchors[1].progress_m <= anchors[0].progress_m:
        result["reasons"] = ["endpoint_geometry_order_conflict"]
        return result
    rows, projections, distances, speeds = [], [], [], []
    # Published RT stop metadata is auxiliary, not a branch-resolution oracle.
    neutral_geometry = replace(geometry, stops=())
    for fix in fixes:
        original = OriginalObservation(**fix["observation"])
        values = (original.reported_at, original.latitude, original.longitude, fix["received_at"])
        reason = None
        if original.position_kind != "observed":
            reason = "non_observed_position"
        elif any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
            reason = "missing_or_invalid_observed_gps"
        elif not -90 <= original.latitude <= 90 or not -180 <= original.longitude <= 180:
            reason = "invalid_coordinates"
        elif (
            not -parameters.future_tolerance_s
            <= fix["received_at"] - original.reported_at
            <= parameters.max_age_s
        ):
            reason = "stale_or_future_gps"
        selected = fix.get("selected_geometry")
        if selected and (
            selected["shape_id"] != geometry.shape_id
            or leg.pattern_id not in selected["pattern_ids"]
        ):
            reason = "tracker_geometry_pattern_incompatible"
        delta, distance = None, None
        if rows and reason is None:
            previous = rows[-1][0]
            delta = original.reported_at - previous.reported_at
            distance = distance_m(
                (previous.latitude, previous.longitude), (original.latitude, original.longitude)
            )
            if delta <= 0:
                reason = "non_increasing_gps_timestamp"
            elif delta > parameters.max_gap_s:
                reason = "observation_gap_excessive"
            elif distance / delta > parameters.max_speed_mps:
                reason = "spatial_jump_excessive"
        if reason:
            result.update(status="rejected", reasons=[reason])
            return result
        neutral = replace(original, stop_id=None, current_stop_sequence=None, current_status=None)
        projection, support = select_projection(
            neutral_geometry,
            neutral,
            parameters,
            projections[-1] if projections else None,
            delta,
        )
        if projection is None:
            result.update(status="rejected", reasons=[support])
            return result
        normalized_id = digest(
            (
                report_hash,
                source,
                vehicle,
                raw["segment_index"],
                fix["snapshot_index"],
                fix["observation_ordinal"],
                original.observation_id,
            )
        )
        normalized = NormalizedObservation(
            normalized_id,
            original.observation_id,
            fix["snapshot_id"],
            source,
            vehicle,
            original.reported_at,
            original.latitude,
            original.longitude,
            True,
            (),
        )
        rows.append((neutral, normalized))
        projections.append(projection)
        if delta is not None:
            distances.append(distance)
            speeds.append(distance / delta)
        result["observations"].append(
            {
                "support_id": normalized_id,
                "fix": fix,
                "projection": asdict(projection),
                "projection_support": support,
            }
        )
    if len(rows) < 2:
        result["reasons"] = ["insufficient_observations"]
        return result
    identity_id = digest((report_hash, source, vehicle, raw["segment_index"], leg.pattern_id))
    identity = CandidateIdentity(
        identity_id,
        (source, vehicle, leg.route_id),
        leg.pattern_id,
        True,
        True,
        False,
        Confidence.CANDIDATE,
        tuple(r[1].normalized_id for r in rows),
        ("user_selected_pattern_hypothesis_not_verified_service",),
    )
    segment = TrajectorySegment(
        digest((identity_id, "od")),
        identity,
        tuple(r[1].normalized_id for r in rows),
        leg.pattern_id,
        rows[0][0].reported_at,
        rows[-1][0].reported_at,
        tuple(distances),
        tuple(speeds),
        (),
        raw["end_reason"],
    )
    events = crossing_events(
        segment, rows, projections, replace(geometry, stops=tuple(anchors)), parameters
    )
    usable = []
    for event in events:
        state = "candidate_crossing" if event.kind == EventKind.CROSSING else "no_evidence"
        reasons = list(event.reasons)
        if (
            event.kind == EventKind.CROSSING
            and event.uncertainty_s > parameters.max_gap_s + 2 * parameters.timestamp_error_s
        ):
            state = "rejected"
            reasons.append("crossing_support_gap_excessive")
        if state == "candidate_crossing":
            usable.append(event)
        result["crossings"].append(
            {
                **asdict(event),
                "status": state,
                "reasons": reasons,
                "support": [
                    entry
                    for entry in result["observations"]
                    if entry["support_id"] in event.support_ids
                ],
                "operationally_validated": False,
            }
        )
    measurement = measure(segment, usable, leg, parameters)
    reasons = [r for r in measurement.reasons if r != "operational_identity_not_verified"]
    ordered = len(usable) == 2 and usable[0].latest_at < usable[1].earliest_at
    if len(usable) == 2 and not ordered:
        reasons.append("endpoint_crossing_intervals_overlap")
    if ordered:
        low, high = measurement.duration_min_s, measurement.duration_max_s
        result["duration"] = {
            "status": "candidate_interval" if not reasons else "indeterminate",
            "duration_min_s": low,
            "duration_max_s": high,
            "uncertainty_s": high - low,
            "estimated_duration_s": measurement.estimated_duration_s if not reasons else None,
            "event_ids": measurement.event_ids,
            "operationally_validated": False,
            "conservative_3a_accepted": measurement.accepted,
            "conservative_3a_reasons": measurement.reasons,
            "waiting_time_s": None,
            "walking_time_s": None,
        }
    result.update(
        status="candidate_interval" if not reasons and ordered else "indeterminate",
        reasons=reasons or ["operational_identity_not_verified"],
    )
    return result


def analyze(
    payload,
    catalog,
    route,
    pattern,
    origin,
    destination,
    *,
    origin_sequence=None,
    destination_sequence=None,
    report_hash=None,
):
    prepare(payload)  # Reuse the tracker report's strict membership/time-order contract.
    if payload["route_id"] != route:
        raise InputError("REPORT_ROUTE_MISMATCH")
    origins = payload.get("origins")
    if origins not in (["synthetic_fixture"], ["saved_real_snapshot"]):
        raise InputError("REPORT_ORIGIN_INVALID")
    info = catalog.info()
    expected = (payload.get("catalog") or {}).get("sha256")
    if not expected or info["sha256"] != expected:
        raise InputError("CATALOG_MISMATCH_OR_NOT_PINNED")
    leg = select_leg(
        catalog, route, pattern, origin, destination, origin_sequence, destination_sequence
    )
    parameters = Parameters()
    geometry, template, geometry_error = pattern_geometry(catalog, leg, parameters)
    report_hash = report_hash or digest(payload)
    results = []
    for candidate in payload["vehicles"]:
        segments = [
            evaluate_segment(
                s,
                candidate["source"],
                candidate["vehicle_id"],
                leg,
                geometry,
                parameters,
                report_hash,
            )
            for s in candidate["segments"]
        ]
        results.append(
            {
                "source": candidate["source"],
                "vehicle_id": candidate["vehicle_id"],
                "tracker_auxiliary_changes": candidate["auxiliary_changes"],
                "segments": segments,
            }
        )
    examined = [s for c in results for s in c["segments"]]
    return {
        "algorithm": VERSION,
        "code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "reused_3a_implementation_sha256": implementation_hash(),
        "parameters": asdict(parameters),
        "leg": asdict(leg),
        "pattern_selection": "explicit" if pattern is not None else "only_route_pattern",
        "catalog": info,
        "origins": origins,
        "input_report_sha256": report_hash,
        "input_tracker_algorithm": payload["algorithm"],
        "input_tracker_code_sha256": payload.get("code_sha256"),
        "input_snapshot_provenance": payload.get("snapshot_provenance", []),
        "static_geometry_template_trip_id": template,
        "geometry_error": geometry_error,
        "static_template_is_not_realtime_trip_match": True,
        "candidates": results,
        "summary": {
            "candidates": len(results),
            "segments": len(examined),
            "crossing_candidates": sum(
                e["status"] == "candidate_crossing" for s in examined for e in s["crossings"]
            ),
            "duration_candidates": sum(s["status"] == "candidate_interval" for s in examined),
            "segment_statuses": dict(Counter(s["status"] for s in examined)),
            "reasons": dict(Counter(r for s in examined for r in s["reasons"])),
        },
        "operationally_validated": False,
        "operational_durations_accepted": 0,
        "network_requests": 0,
        "new_gps_captures": 0,
        "limitations": [
            "pattern_is_explicit_hypothesis_not_verified_service",
            "vehicle_id_not_verified_physical_identity",
            "no_service_calendar_or_operational_trip_validation",
            "no_arrival_boarding_waiting_walking_or_eta",
            "input_report_trusted_PBs_not_reverified_here",
            "no_links_between_tracker_segments",
        ],
    }


def run(report_path, catalog_path, route, pattern, origin, destination, **occurrences):
    data = Path(report_path).read_bytes()
    payload = json.loads(data)
    with Catalog(catalog_path) as catalog:
        result = analyze(
            payload,
            catalog,
            route,
            pattern,
            origin,
            destination,
            report_hash=hashlib.sha256(data).hexdigest(),
            **occurrences,
        )
    result["input_report_path"] = str(Path(report_path).resolve())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report")
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--route", required=True)
    parser.add_argument("--pattern")
    parser.add_argument("--origin", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--origin-sequence", type=int)
    parser.add_argument("--destination-sequence", type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        output = pilot_path(project_path(args.output))
        if output.exists():
            raise InputError("OUTPUT_EXISTS")
        report = run(
            project_path(args.report),
            project_path(args.catalog),
            args.route,
            args.pattern,
            args.origin,
            args.destination,
            origin_sequence=args.origin_sequence,
            destination_sequence=args.destination_sequence,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, json.loads(canonical(report)))
        print(
            "Análisis OD experimental: "
            + canonical(
                {**report["summary"], "network_requests": 0, "operationally_validated": False}
            )
        )
        return 0
    except InputError as error:
        parser.exit(
            2, f"Entrada OD rechazada [{error}]; revise selección, versión y destino privado.\n"
        )
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error):
        parser.exit(2, "Entrada/salida OD inválida o inaccesible; sin adquisición ni reintento.\n")


if __name__ == "__main__":
    raise SystemExit(main())
