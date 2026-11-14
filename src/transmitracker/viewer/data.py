"""Pure visual preparation, independent of Tk and of tracking decisions."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from transmitracker.catalog.queries import Catalog
from transmitracker.research.route_tracker import VERSION

STATES = {
    "movimiento_candidato": ("Movimiento candidato", "#2dd4bf"),
    "estacionario": ("Bajo movimiento", "#60a5fa"),
    "interrumpido": ("Interrumpido", "#fbbf24"),
    "ambiguo": ("Ambiguo", "#c084fc"),
    "descartado": ("Descartado", "#fb7185"),
}


class ViewerError(ValueError):
    """Safe fixed messages only, with no payload or exception text."""


@dataclass(frozen=True)
class Fix:
    key: tuple
    point: tuple[float, float] | None
    timestamp: float | None
    received_at: float | None
    feed_as_of: float | None
    position_kind: str


@dataclass(frozen=True)
class Segment:
    index: int
    state: str
    activity: str
    fixes: tuple[Fix, ...]
    changes: int
    distance: float
    progress: float | None
    start: str
    end: str
    pattern_ambiguous: bool
    patterns: tuple[str, ...]
    shapes: tuple[str, ...]
    alternatives: tuple[str, ...]


@dataclass(frozen=True)
class Candidate:
    source: str
    vehicle: str
    fixes: tuple[Fix, ...]
    segments: tuple[Segment, ...]
    incidents: tuple[str, ...]

    def segment_at(self, fix):
        return next((s for s in self.segments if any(f.key == fix.key for f in s.fixes)), None)


@dataclass(frozen=True)
class Shape:
    identity: str
    patterns: tuple[str, ...]
    points: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class Scene:
    route: str
    candidates: tuple[Candidate, ...]
    shapes: tuple[Shape, ...]
    note: str
    synthetic: bool

    def candidate(self, index):
        if type(index) is not int or not 0 <= index < len(self.candidates):
            raise ViewerError("Seleccione un candidato existente.")
        return self.candidates[index]


def _text(value):
    if not isinstance(value, str) or not value:
        raise ValueError("text")
    return value


def _number(value, optional=False):
    if value is None and optional:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("number")
    return value


def _integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("integer")
    return value


def _list(value):
    if not isinstance(value, list):
        raise ValueError("list")
    return value


def _fix(value, source, vehicle, route):
    row = value["observation"]
    if (row["source"], row["vehicle_id"], row["route_id"]) != (source, vehicle, route):
        raise ValueError("association")
    lat, lon = (_number(row[k], optional=True) for k in ("latitude", "longitude"))
    kind = _text(row["position_kind"])
    point = (
        (lat, lon)
        if kind == "observed"
        and lat is not None
        and lon is not None
        and -90 <= lat <= 90
        and -180 <= lon <= 180
        else None
    )
    return Fix(
        (
            _integer(value["snapshot_index"]),
            _integer(value["observation_ordinal"]),
            _text(row["observation_id"]),
        ),
        point,
        _number(row["reported_at"], optional=True),
        _number(value["received_at"], optional=True),
        _number(value["feed_as_of"], optional=True),
        kind,
    )


def prepare(payload, shapes=(), note="Sin catálogo: no se dibuja un trazado supuesto."):
    """Keep capture order and reported segment membership, never create a link."""
    try:
        if payload["algorithm"] != VERSION or payload["operationally_verified"] is not False:
            raise ValueError("contract")
        if payload["arrivals_boarding_travel_durations_inferred"] is not False:
            raise ValueError("contract")
        if payload.get("catalog") is not None and not isinstance(payload["catalog"], dict):
            raise ValueError("catalog metadata")
        route = _text(payload["route_id"])
        candidates, seen = [], set()
        for value in _list(payload["vehicles"]):
            source, vehicle = _text(value["source"]), _text(value["vehicle_id"])
            if (source, vehicle) in seen:
                raise ValueError("duplicate candidate")
            seen.add((source, vehicle))
            originals = [
                _fix(f, source, vehicle, route)
                for f in _list(value["all_source_vehicle_sightings"])
                if f["observation"]["route_id"] == route
            ]
            originals.sort(key=lambda f: f.key[:2])
            by_key = {f.key: f for f in originals}
            if len(by_key) != len(originals):
                raise ValueError("duplicate occurrence")
            segments, used, indices = [], set(), set()
            for item in _list(value["segments"]):
                state = item["state"]
                if state not in STATES or item["activity_candidate"] not in STATES:
                    raise ValueError("state")
                index = _integer(item["segment_index"])
                if index in indices or type(item["pattern_ambiguous"]) is not bool:
                    raise ValueError("segment")
                indices.add(index)
                fixes = tuple(_fix(f, source, vehicle, route) for f in _list(item["fixes"]))
                if not fixes:
                    raise ValueError("empty segment")
                for fix in fixes:
                    if by_key.get(fix.key) != fix or fix.key in used:
                        raise ValueError("unsupported link")
                    used.add(fix.key)
                if [f.key[:2] for f in fixes] != sorted(f.key[:2] for f in fixes):
                    raise ValueError("capture order")
                if len(fixes) > 1 and any(
                    a.timestamp is None or b.timestamp is None or b.timestamp <= a.timestamp
                    for a, b in zip(fixes, fixes[1:], strict=False)
                ):
                    raise ValueError("segment GPS order")
                patterns, shape_ids, alternatives = set(), set(), set()
                for f in item["fixes"]:
                    for option in f.get("shape_candidates", []):
                        identity = _text(option["shape_id"])
                        members = tuple(_text(p) for p in _list(option["pattern_ids"]))
                        alternatives.add(
                            f"{identity}: {_text(option['reason'])} · patrones {', '.join(members)}"
                        )
                    selected = f.get("selected_geometry")
                    if selected:
                        shape_ids.add(_text(selected["shape_id"]))
                        patterns.update(_text(p) for p in _list(selected["pattern_ids"]))
                segments.append(
                    Segment(
                        index,
                        state,
                        item["activity_candidate"],
                        fixes,
                        _integer(item["position_changes"]),
                        _number(item["sampled_distance_m"]),
                        _number(item["geometric_progress_m"], optional=True),
                        _text(item["start_reason"]),
                        _text(item["end_reason"]),
                        item["pattern_ambiguous"],
                        tuple(sorted(patterns)),
                        tuple(sorted(shape_ids)),
                        tuple(sorted(alternatives)),
                    )
                )
            candidates.append(
                Candidate(
                    source,
                    vehicle,
                    tuple(originals),
                    tuple(segments),
                    tuple(_text(i["reason"]) for i in _list(value["incidents"])),
                )
            )
        origins = payload.get("origins", [])
        synthetic = origins == ["synthetic_fixture"]
        return Scene(route, tuple(candidates), tuple(shapes), note, synthetic)
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ViewerError(
            "Reporte incompatible o inválido; revise el formato del rastreador."
        ) from None


def load(report_path, catalog_path=None):
    try:
        payload = json.loads(Path(report_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ViewerError("No se pudo leer el reporte JSON local.") from None
    scene = prepare(payload)
    if catalog_path is None:
        return scene
    import sqlite3

    try:
        catalog = Catalog(catalog_path)
        try:
            expected = (payload.get("catalog") or {}).get("sha256")
            if expected and catalog.info()["sha256"] != expected:
                raise ViewerError(
                    "La versión del catálogo no coincide con la fijada en el reporte."
                )
            patterns = {}
            for row in catalog.connection.execute(
                "SELECT shape_id,pattern_id FROM patterns WHERE route_id=? ORDER BY pattern_id",
                (scene.route,),
            ):
                patterns.setdefault(row["shape_id"], []).append(row["pattern_id"])
            shapes = []
            for shape_id, members in patterns.items():
                points = tuple(
                    (row[0], row[1])
                    for row in catalog.connection.execute(
                        "SELECT latitude,longitude FROM shape_points WHERE shape_id=? ORDER BY sequence",
                        (shape_id,),
                    )
                )
                if len(points) >= 2 and all(
                    type(a) in (int, float)
                    and type(b) in (int, float)
                    and math.isfinite(a)
                    and math.isfinite(b)
                    and -90 <= a <= 90
                    and -180 <= b <= 180
                    for a, b in points
                ):
                    shapes.append(Shape(shape_id, tuple(members), points))
            note = (
                "Versión GTFS coincide por hash. Todos los shapes/patrones; sin elegir servicio."
                if expected
                else "Catálogo no fijado en reporte: geometrías solo como contexto."
            )
            if not shapes:
                note += " Sin geometría utilizable para esta ruta."
            return prepare(payload, shapes, note)
        finally:
            catalog.close()
    except ViewerError:
        raise
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        raise ViewerError("Catálogo local incompatible o inaccesible; no se sustituyó.") from None


@dataclass(frozen=True)
class Transform:
    """Local equirectangular drawing only; not a distance/precision estimator."""

    latitude: float
    longitude: float
    scale: float
    width: float
    height: float

    @classmethod
    def fit(cls, points, width, height):
        points = tuple(points) or ((0.0, 0.0),)
        lat = (min(p[0] for p in points) + max(p[0] for p in points)) / 2
        lon = (min(p[1] for p in points) + max(p[1] for p in points)) / 2
        cosine = max(0.01, math.cos(math.radians(lat)))
        dx = max(0.001, (max(p[1] for p in points) - min(p[1] for p in points)) * cosine)
        dy = max(0.001, max(p[0] for p in points) - min(p[0] for p in points))
        return cls(lat, lon, min(max(1, width - 60) / dx, max(1, height - 60) / dy), width, height)

    def point(self, point, zoom=1, pan=(0, 0)):
        return (
            self.width / 2
            + (point[1] - self.longitude)
            * math.cos(math.radians(self.latitude))
            * self.scale
            * zoom
            + pan[0],
            self.height / 2 - (point[0] - self.latitude) * self.scale * zoom + pan[1],
        )
