"""Inspect GTFS ZIP/CSV without extracting files or retaining stop_times in RAM."""

import csv
import io
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from transmitracker.gtfs import FeedError

REQUIRED = {
    "agency.txt": {"agency_name", "agency_url", "agency_timezone"},
    "routes.txt": {"route_id", "route_type"},
    "stops.txt": {"stop_id", "stop_name"},
    "trips.txt": {"trip_id", "route_id", "service_id"},
    "stop_times.txt": {"trip_id", "stop_id", "stop_sequence"},
}


@dataclass
class StaticFeed:
    routes: dict = field(default_factory=dict)
    stops: dict = field(default_factory=dict)
    trips: dict = field(default_factory=dict)
    sample_trip_id: str | None = None
    sample_stops: list = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def _rows(archive: ZipFile, name: str):
    with archive.open(name) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as text:
        reader = csv.DictReader(text)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED.get(name, set()) - columns
        if missing:
            raise FeedError(f"{name}: missing columns {sorted(missing)}")
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise FeedError(f"{name}: malformed CSV row {reader.line_num}")
            yield row


def _index(archive: ZipFile, name: str, key: str) -> dict:
    result = {}
    for row in _rows(archive, name):
        identity = row[key]
        if not identity or identity in result:
            raise FeedError(f"{name}: empty or duplicate {key}: {identity!r}")
        result[identity] = row
    if not result:
        raise FeedError(f"{name}: no records")
    return result


def read_static(path: Path, *, max_uncompressed: int = 3 * 1024**3) -> StaticFeed:
    """Structural and selected relational checks only; no service selection.

    Every stop_time is streamed for row counts/references. Only the first trip's
    stop sequence is retained as an example. Shapes are counted, not loaded.
    """
    try:
        with ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise FeedError("Duplicate ZIP members")
            missing = set(REQUIRED) - set(names)
            if missing:
                raise FeedError(f"Missing GTFS files: {sorted(missing)}")
            if not {"calendar.txt", "calendar_dates.txt"} & set(names):
                raise FeedError("Missing calendar.txt/calendar_dates.txt")
            if sum(member.file_size for member in archive.infolist()) > max_uncompressed:
                raise FeedError("ZIP uncompressed size exceeds limit")
            feed = StaticFeed()
            feed.routes = _index(archive, "routes.txt", "route_id")
            feed.stops = _index(archive, "stops.txt", "stop_id")
            feed.trips = _index(archive, "trips.txt", "trip_id")
            feed.sample_trip_id = next(iter(feed.trips))
            counts = {
                name: len(index)
                for name, index in (
                    ("routes.txt", feed.routes),
                    ("stops.txt", feed.stops),
                    ("trips.txt", feed.trips),
                )
            }
            errors = Counter()
            services = set()
            optional_samples = {}
            for name in (
                "agency.txt",
                "calendar.txt",
                "calendar_dates.txt",
                "feed_info.txt",
                "frequencies.txt",
            ):
                if name not in names:
                    continue
                count = 0
                samples = []
                for row in _rows(archive, name):
                    count += 1
                    if name == "agency.txt" or len(samples) < 3:
                        samples.append(row)
                    if name in {"calendar.txt", "calendar_dates.txt"}:
                        services.add(row.get("service_id"))
                counts[name] = count
                optional_samples[name] = samples
            if not counts["agency.txt"]:
                raise FeedError("agency.txt: no records")
            for trip in feed.trips.values():
                errors["trip_route_missing"] += trip["route_id"] not in feed.routes
                errors["trip_service_missing"] += trip["service_id"] not in services
            for stop in feed.stops.values():
                parent = stop.get("parent_station")
                errors["parent_station_missing"] += bool(parent and parent not in feed.stops)
            stop_time_count = 0
            served_stops, served_routes = set(), set()
            agency_stops = {}
            for row in _rows(archive, "stop_times.txt"):
                stop_time_count += 1
                trip = feed.trips.get(row["trip_id"])
                errors["stop_time_trip_missing"] += trip is None
                errors["stop_time_stop_missing"] += row["stop_id"] not in feed.stops
                served_stops.add(row["stop_id"])
                if trip:
                    served_routes.add(trip["route_id"])
                    agency_id = feed.routes.get(trip["route_id"], {}).get("agency_id", "")
                    agency_stops.setdefault(agency_id, set()).add(row["stop_id"])
                try:
                    sequence = int(row["stop_sequence"])
                    if sequence < 0:
                        raise ValueError
                except ValueError as exc:
                    raise FeedError("Invalid stop_sequence") from exc
                if row["trip_id"] == feed.sample_trip_id:
                    feed.sample_stops.append({**row, "stop_sequence": sequence})
            if not stop_time_count:
                raise FeedError("stop_times.txt: no records")
            counts["stop_times.txt"] = stop_time_count
            if "shapes.txt" in names:
                counts["shapes.txt"] = sum(1 for _ in _rows(archive, "shapes.txt"))
            feed.sample_stops.sort(key=lambda row: row["stop_sequence"])
            feed.summary = {
                "validation_scope": "structural_and_selected_references_only",
                "basic_checks_passed": not any(errors.values()),
                "counts": counts,
                "reference_errors": dict(errors),
                "route_types": dict(Counter(row["route_type"] for row in feed.routes.values())),
                "agencies": optional_samples.get("agency.txt", []),
                "agency_count": counts["agency.txt"],
                "coverage_by_agency": [
                    {
                        "agency_id": agency.get("agency_id", ""),
                        "agency_name": agency["agency_name"],
                        "routes": sum(
                            r.get("agency_id", "") == agency.get("agency_id", "")
                            for r in feed.routes.values()
                        ),
                        "stops_in_stop_times": len(
                            agency_stops.get(agency.get("agency_id", ""), set())
                        ),
                    }
                    for agency in optional_samples["agency.txt"]
                ],
                "sample_optional_tables": optional_samples,
                "routes_with_stop_times": len(served_routes),
                "stops_in_stop_times": len(served_stops),
                "sample_trip": feed.trips[feed.sample_trip_id],
                "sample_trip_stops": feed.sample_stops,
                "files": names,
            }
            return feed
    except (BadZipFile, UnicodeError, csv.Error, KeyError, OSError, RuntimeError) as exc:
        raise FeedError(f"Invalid GTFS ZIP/CSV: {exc}") from exc
