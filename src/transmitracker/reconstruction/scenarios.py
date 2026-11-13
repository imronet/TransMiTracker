"""Explicit synthetic generators for offline replay, never a provider fallback."""

import csv
import io
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from transmitracker.catalog.importer import import_catalog
from transmitracker.profiles.models import Leg
from transmitracker.reconstruction.io import snapshot_from_rows
from transmitracker.reconstruction.models import IdentityEvidence
from transmitracker.research.temporal import EARTH

ORIGIN = (4.65, -74.06)
PATHS = {
    "line": ([(0, 0), (2200, 0)], [("A", 135), ("B", 435), ("C", 835), ("Z", 2000)]),
    "branch": (
        [(0, 0), (200, -100), (600, -300), (1400, -300), (2200, -300)],
        [("A", 135), ("B", 435), ("C", 835), ("Z", 2000)],
    ),
    "loop": (
        [(0, 0), (400, 0), (400, 400), (0, 400), (0, 0), (600, 0)],
        [("X", 200), ("Y", 800), ("X", 1800), ("Z", 2150)],
    ),
    "cross": (
        [(0, 0), (400, 400), (0, 400), (400, 0)],
        [("A", 100), ("B", 600), ("C", 1200), ("Z", 1450)],
    ),
}


def ll(point):
    return ORIGIN[0] + math.degrees(point[1] / EARTH), ORIGIN[1] + math.degrees(
        point[0] / (EARTH * math.cos(math.radians(ORIGIN[0])))
    )


def point_at(path, progress):
    points = PATHS[path][0]
    for a, b in zip(points, points[1:], strict=False):
        length = math.dist(a, b)
        if progress <= length:
            ratio = max(0, min(1, progress / length))
            return a[0] + ratio * (b[0] - a[0]), a[1] + ratio * (b[1] - a[1])
        progress -= length
    return points[-1]


def stop_id(path, label):
    return f"DEMO_{path.upper()}_{label}"


def route_id(path):
    # The branch is intentionally another pattern of the same route, never merged by route alone.
    return "DEMO_LINE" if path == "branch" else "DEMO_" + path.upper()


def trip_id(path):
    return "DEMO_TRIP_" + path.upper()


def create_catalog(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    tables = {
        "agency.txt": (
            ["agency_id", "agency_name", "agency_timezone"],
            [["DEMO", "Synthetic 3A agency", "America/Bogota"]],
        ),
        "routes.txt": (
            ["route_id", "route_short_name", "route_long_name", "route_type"],
            [["DEMO_" + p.upper(), p, "Synthetic " + p, 3] for p in PATHS if p != "branch"],
        ),
        "stops.txt": (["stop_id", "stop_name", "stop_lat", "stop_lon"], []),
        "trips.txt": (["route_id", "service_id", "trip_id", "direction_id", "shape_id"], []),
        "stop_times.txt": (
            [
                "trip_id",
                "arrival_time",
                "departure_time",
                "stop_id",
                "stop_sequence",
                "pickup_type",
                "drop_off_type",
                "shape_dist_traveled",
            ],
            [],
        ),
        "shapes.txt": (
            [
                "shape_id",
                "shape_pt_lat",
                "shape_pt_lon",
                "shape_pt_sequence",
                "shape_dist_traveled",
            ],
            [],
        ),
        "calendar.txt": (
            [
                "service_id",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
                "start_date",
                "end_date",
            ],
            [["DEMO_DAILY", 1, 1, 1, 1, 1, 1, 1, "20261101", "20261231"]],
        ),
    }
    stops = {}
    for path, (points, occurrences) in PATHS.items():
        progress = 0.0
        for index, point in enumerate(points):
            if index:
                progress += math.dist(point, points[index - 1])
            lat, lon = ll(point)
            tables["shapes.txt"][1].append([path, lat, lon, index, progress])
        variants = [(trip_id(path), 8 * 3600)]
        if path == "line":
            variants += [
                ("DEMO_TRIP_CHANGED", 8 * 3600),
                ("DEMO_TRIP_MIDNIGHT", 23 * 3600 + 59 * 60 + 30),
            ]
        for identity, base in variants:
            tables["trips.txt"][1].append([route_id(path), "DEMO_DAILY", identity, 0, path])
            for index, (label, along) in enumerate(occurrences, 1):
                key = stop_id(path, label)
                lat, lon = ll(point_at(path, along))
                stops[key] = [key, "Synthetic " + key, lat, lon]
                seconds = base + int(along / 10)
                clock = f"{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}"
                tables["stop_times.txt"][1].append(
                    [identity, clock, clock, key, index * 10, 0, 0, along]
                )
    tables["stops.txt"][1].extend(stops.values())
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, (header, rows) in tables.items():
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)
            entry = ZipInfo(name, date_time=(2026, 11, 12, 0, 0, 0))
            entry.compress_type = ZIP_DEFLATED
            archive.writestr(entry, stream.getvalue().encode("utf-8"))
    path = directory / "synthetic_catalog_v1.zip"
    if path.exists() and path.read_bytes() != buffer.getvalue():
        raise ValueError("Synthetic fixture version changed; use a new output directory/version")
    if not path.exists():
        path.write_bytes(buffer.getvalue())
    target = directory / "synthetic_catalog_v1.sqlite3"
    import_catalog(path, target)
    return target


@dataclass(frozen=True)
class SyntheticCase:
    name: str
    snapshots: tuple
    evidence: tuple
    legs: tuple
    truth_events: tuple[dict, ...]
    must_reject_measurement: bool
    truth_measurable: bool


def specs():
    root = Path(__file__).resolve().parents[3]
    return json.loads((root / "tests/fixtures/phase3a/scenarios.json").read_text(encoding="utf-8"))[
        "cases"
    ]


def build_case(catalog, spec, gap=20):
    path, fault = spec["path"], spec.get("fault")
    base = datetime.fromisoformat(
        "2026-11-12T23:59:30-05:00" if fault == "midnight" else "2026-11-12T08:00:00-05:00"
    )
    source = "synthetic://phase3a/" + spec["name"]
    paths = [path] + ([spec["second_vehicle"]] if spec.get("second_vehicle") else [])
    lengths = [PATHS[p][1][2][1] for p in paths]
    duration = max(lengths) / 10 + 30 + (30 if fault == "dwell" else 0)
    offsets = [float(v) for v in range(0, int(math.ceil(duration / gap)) * gap + 1, gap)]
    if path in ("loop", "cross"):
        # End before the terminal; do not manufacture an IN_TRANSIT_TO report beyond its stop.
        offsets = [value for value in offsets if value * 10 < PATHS[path][1][-1][1]]
    if fault == "dwell":
        offsets = sorted(set(offsets + [50.0, 60.0, 70.0]))
    if fault == "ambiguous":
        offsets = [0.0, 20.0]
    if fault == "short":
        offsets = offsets[:2]
    sha = catalog.info()["sha256"]
    frames, evidence, legs, truth = [], [], [], []
    for number, geometry_path in enumerate(paths):
        identity = "DEMO_V" + str(number + 1)
        trip = "DEMO_TRIP_MIDNIGHT" if fault == "midnight" else trip_id(geometry_path)
        pattern = catalog.connection.execute(
            "SELECT pattern_id FROM trips WHERE trip_id=?", (trip,)
        ).fetchone()[0]
        start = base.strftime("%H:%M:%S")
        evidence.append(
            IdentityEvidence(
                source,
                identity,
                trip,
                route_id(geometry_path),
                "20261112",
                start,
                pattern,
                base.timestamp() - 1,
                base.timestamp() + max(offsets) + 1,
                "synthetic_generator_identity_" + identity,
            )
        )
        occurrences = PATHS[geometry_path][1]
        legs.append(
            Leg(
                stop_id(geometry_path, occurrences[0][0]),
                route_id(geometry_path),
                pattern,
                0,
                10,
                stop_id(geometry_path, occurrences[2][0]),
                30,
            )
        )
        for index, (label, progress) in enumerate(occurrences[:3], 1):
            crossing = progress / 10 + (30 if fault == "dwell" and progress > 435 else 0)
            if crossing <= max(offsets):
                truth.append(
                    {
                        "vehicle_id": identity,
                        "pattern_id": pattern,
                        "stop_id": stop_id(geometry_path, label),
                        "sequence": index * 10,
                        "at": base.timestamp() + crossing,
                    }
                )
    for offset in offsets:
        rows = []
        for number, geometry_path in enumerate(paths):
            progress = offset * 10
            if fault == "dwell":
                progress = (
                    435
                    if 43.5 <= offset <= 73.5
                    else (offset - 30) * 10
                    if offset > 73.5
                    else progress
                )
            if fault == "ambiguous":
                progress = math.sqrt(200**2 + 200**2)
            if fault == "reverse" and offset == 40:
                progress = 180
            if fault == "speed" and offset == 40:
                progress = 1500
            point = point_at(geometry_path, progress)
            if fault == "noise":
                point = (
                    point[0] + 6 * math.sin(offset * 0.2),
                    point[1] + 3 * math.cos(offset * 0.17),
                )
            if fault == "off_shape" and offset == 40:
                point = (point[0], point[1] + 1000)
            lat, lon = ll(point)
            if fault == "coordinates" and offset == 40:
                lat = 999
            occurrences = PATHS[geometry_path][1]
            target_index = next(
                (i for i, (_, p) in enumerate(occurrences) if p >= progress), len(occurrences) - 1
            )
            stopped = fault == "dwell" and 43.5 <= offset <= 73.5
            ts = base.timestamp() + offset
            if fault == "stale":
                ts -= 1000
            if fault == "clock" and offset >= 40:
                ts -= 200
            rows.append(
                {
                    "entity_id": "SYNTHETIC_ENTITY_" + str(number),
                    "vehicle_id": "DEMO_V" + str(number + 1),
                    "trip_id": "DEMO_TRIP_CHANGED"
                    if fault == "trip" and offset >= 40
                    else "DEMO_TRIP_MIDNIGHT"
                    if fault == "midnight"
                    else trip_id(geometry_path),
                    "route_id": route_id(geometry_path),
                    "direction_id": 0,
                    "start_date": "20261112",
                    "start_time": datetime.fromtimestamp(
                        base.timestamp() + offset, base.tzinfo
                    ).strftime("%H:%M:%S")
                    if fault == "start"
                    else base.strftime("%H:%M:%S"),
                    "reported_at": ts,
                    "latitude": lat,
                    "longitude": lon,
                    "stop_id": stop_id(geometry_path, occurrences[target_index][0]),
                    "current_stop_sequence": (target_index + 1) * 10,
                    "current_status": None
                    if fault == "ambiguous"
                    else "STOPPED_AT"
                    if stopped
                    else "IN_TRANSIT_TO",
                }
            )
        if fault == "missing" and offset == 40:
            rows = []
        if fault == "duplicates" and rows:
            rows.append(dict(rows[0]))
        if fault == "conflict" and offset == 40:
            rows.append({**rows[0], "longitude": rows[0]["longitude"] + 0.001})
        frames.append(
            snapshot_from_rows(
                source=source,
                endpoint=None,
                catalog_sha256=sha,
                origin="synthetic_fixture",
                rows=rows,
                feed_as_of=base.timestamp() + offset,
                received_at=base.timestamp() + offset + 1,
                provenance={
                    "fixture": "phase3a/scenarios.json",
                    "scenario": spec["name"],
                    "gap_seconds": gap,
                },
            )
        )
    if fault == "out_of_order" and len(frames) > 3:
        frames[1], frames[2] = frames[2], frames[1]
    return SyntheticCase(
        spec["name"],
        tuple(frames),
        tuple(evidence),
        tuple(legs),
        tuple(truth),
        spec.get("must_reject_measurement", False),
        not spec.get("must_reject_measurement", False),
    )
