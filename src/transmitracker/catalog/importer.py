"""Atomic ZIP-to-SQLite importer. Large tables use bounded executemany batches."""

import csv
import hashlib
import io
import json
import sqlite3
import time
import uuid
from datetime import datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from transmitracker.catalog import CatalogError
from transmitracker.catalog.common import BOGOTA, file_hash, gtfs_seconds
from transmitracker.catalog.schema import INDEXES, SCHEMA, SCHEMA_VERSION

REQUIRED = {
    "agency.txt": {"agency_name", "agency_timezone"},
    "routes.txt": {"route_id", "route_type"},
    "stops.txt": {"stop_id", "stop_name"},
    "trips.txt": {"trip_id", "route_id", "service_id"},
    "stop_times.txt": {"trip_id", "stop_id", "stop_sequence"},
    "shapes.txt": {"shape_id", "shape_pt_sequence", "shape_pt_lat", "shape_pt_lon"},
    "calendar.txt": {
        "service_id",
        "start_date",
        "end_date",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    },
    "calendar_dates.txt": {"service_id", "date", "exception_type"},
    "frequencies.txt": {"trip_id", "start_time", "end_time", "headway_secs"},
}


def rows(archive, name):
    if name not in archive.namelist():
        return
    with (
        archive.open(name) as raw,
        io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream,
    ):
        reader = csv.DictReader(stream)
        missing = REQUIRED.get(name, set()) - set(reader.fieldnames or [])
        if missing:
            raise CatalogError(f"{name}: missing columns {sorted(missing)}")
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise CatalogError(f"{name}: malformed CSV row {reader.line_num}")
            yield row


def nullable(value):
    return value if value != "" else None


def integer(value, default=None):
    return int(value) if value else default


def number(value):
    return float(value) if value else None


def day(value):
    if len(value) != 8 or not value.isdigit():
        raise CatalogError(f"Invalid service date {value!r}")
    datetime.strptime(value, "%Y%m%d")
    return value


def batch_insert(connection, sql, values, batch_size):
    batch, count = [], 0
    for value in values:
        batch.append(value)
        if len(batch) >= batch_size:
            connection.executemany(sql, batch)
            count += len(batch)
            batch.clear()
    if batch:
        connection.executemany(sql, batch)
        count += len(batch)
    return count


def _patterns(connection):
    """Ordered scan retains only one trip's stops and small pattern signatures."""
    known, current, stops = {}, None, []
    trip_data = {
        row[0]: row[1:]
        for row in connection.execute("SELECT trip_pk,route_id,direction_id,shape_id FROM trips")
    }
    updates = []

    def finish(trip_pk, sequence):
        route, direction, shape = trip_data[trip_pk]
        signature = json.dumps(
            [route, direction, shape, [list(r[:4]) for r in sequence]],
            separators=(",", ":"),
            ensure_ascii=False,
        )
        pattern_id = hashlib.sha256(signature.encode("utf-8")).hexdigest()
        if pattern_id not in known:
            connection.execute(
                "INSERT INTO patterns VALUES (?,?,?,?,?)",
                (pattern_id, route, direction, shape, len(sequence)),
            )
            connection.executemany(
                "INSERT INTO pattern_stops VALUES (?,?,?,?,?)",
                [(pattern_id, *r[:4]) for r in sequence],
            )
            known[pattern_id] = True
        first_departure = sequence[0][5]
        max_seconds = max((v for r in sequence for v in r[4:6] if v is not None), default=0)
        updates.append((pattern_id, first_departure, max_seconds, trip_pk))
        if len(updates) >= 5000:
            connection.executemany(
                "UPDATE trips SET pattern_id=?,first_departure=?,max_seconds=? WHERE trip_pk=?",
                updates,
            )
            updates.clear()

    for row in connection.execute(
        "SELECT trip_pk,sequence,stop_id,pickup_type,drop_off_type,arrival,departure FROM stop_times ORDER BY trip_pk,sequence"
    ):
        if current is not None and row[0] != current:
            finish(current, stops)
            stops = []
        current = row[0]
        stops.append(row[1:])
    if current is not None:
        finish(current, stops)
    if updates:
        connection.executemany(
            "UPDATE trips SET pattern_id=?,first_departure=?,max_seconds=? WHERE trip_pk=?", updates
        )
    return len(known)


def import_catalog(
    zip_path: Path,
    database: Path,
    *,
    source_url: str | None = None,
    batch_size: int = 10_000,
    progress=None,
) -> dict:
    started = time.perf_counter()
    zip_path, database = Path(zip_path).resolve(), Path(database).resolve()
    if not 1 <= batch_size <= 100_000:
        raise CatalogError("batch_size must be between 1 and 100000")
    sha = file_hash(zip_path)
    if database.exists():
        try:
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as existing:
                version = existing.execute("PRAGMA user_version").fetchone()[0]
                row = existing.execute(
                    "SELECT sha256,timings_json FROM catalog_versions"
                ).fetchone()
                if version != SCHEMA_VERSION or not row or row[0] != sha:
                    raise CatalogError(
                        "Database contains a different catalog/schema; use a new database path"
                    )
                return {
                    "status": "reused",
                    "sha256": sha,
                    "database": str(database),
                    "elapsed_seconds": time.perf_counter() - started,
                    "database_bytes": database.stat().st_size,
                    "original_timings": json.loads(row[1]),
                }
        except sqlite3.Error as exc:
            raise CatalogError(f"Existing database is not a compatible catalog: {exc}") from exc
    database.parent.mkdir(parents=True, exist_ok=True)
    staging = database.with_name(database.name + f".import-{uuid.uuid4().hex}.sqlite3")
    counts, timings = {}, {}
    connection = None
    try:
        connection = sqlite3.connect(staging)
        connection.execute("PRAGMA cache_size=-65536")
        connection.execute("PRAGMA temp_store=FILE")
        # No network or user-facing database exists until all checks succeed.
        connection.executescript(SCHEMA)
        with ZipFile(zip_path) as archive, connection:
            names = archive.namelist()
            if len(names) != len(set(names)):
                raise CatalogError("Duplicate ZIP members")
            missing = set(
                ("agency.txt", "routes.txt", "stops.txt", "trips.txt", "stop_times.txt")
            ) - set(names)
            if missing or not {"calendar.txt", "calendar_dates.txt"} & set(names):
                raise CatalogError(f"Missing required GTFS files or calendar: {sorted(missing)}")
            if sum(member.file_size for member in archive.infolist()) > 3 * 1024**3:
                raise CatalogError("Uncompressed ZIP exceeds 3 GiB limit")

            def load(table, sql, values):
                step = time.perf_counter()
                counts[table] = batch_insert(connection, sql, values, batch_size)
                timings[table] = time.perf_counter() - step
                if progress:
                    progress(f"{table}: {counts[table]:,} rows ({timings[table]:.2f}s)")

            agencies = list(rows(archive, "agency.txt"))
            if not agencies or any(r["agency_timezone"] != "America/Bogota" for r in agencies):
                raise CatalogError(
                    "This catalog currently supports agency_timezone America/Bogota only"
                )
            load(
                "agencies",
                "INSERT INTO agencies VALUES (?,?,?)",
                (
                    (nullable(r.get("agency_id", "")), r["agency_name"], r["agency_timezone"])
                    for r in agencies
                ),
            )
            load(
                "routes",
                "INSERT INTO routes VALUES (?,?,?,?,?)",
                (
                    (
                        r["route_id"],
                        nullable(r.get("agency_id", "")),
                        r.get("route_short_name", ""),
                        r.get("route_long_name", ""),
                        int(r["route_type"]),
                    )
                    for r in rows(archive, "routes.txt")
                ),
            )
            load(
                "stops",
                "INSERT INTO stops VALUES (?,?,?,?,?,?,?,?)",
                (
                    (
                        r["stop_id"],
                        nullable(r.get("stop_code", "")),
                        r["stop_name"],
                        number(r.get("stop_lat", "")),
                        number(r.get("stop_lon", "")),
                        integer(r.get("location_type", ""), 0),
                        nullable(r.get("parent_station", "")),
                        nullable(r.get("platform_code", "")),
                    )
                    for r in rows(archive, "stops.txt")
                ),
            )
            load(
                "calendar",
                "INSERT INTO calendar VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    (
                        r["service_id"],
                        *(
                            int(r[k])
                            for k in (
                                "monday",
                                "tuesday",
                                "wednesday",
                                "thursday",
                                "friday",
                                "saturday",
                                "sunday",
                            )
                        ),
                        day(r["start_date"]),
                        day(r["end_date"]),
                    )
                    for r in rows(archive, "calendar.txt")
                ),
            )
            load(
                "calendar_dates",
                "INSERT INTO calendar_dates VALUES (?,?,?)",
                (
                    (r["service_id"], day(r["date"]), int(r["exception_type"]))
                    for r in rows(archive, "calendar_dates.txt")
                ),
            )
            connection.execute(
                "INSERT INTO services SELECT service_id FROM calendar UNION SELECT service_id FROM calendar_dates"
            )
            load(
                "trips",
                "INSERT INTO trips(trip_id,route_id,service_id,headsign,direction_id,shape_id) VALUES (?,?,?,?,?,?)",
                (
                    (
                        r["trip_id"],
                        r["route_id"],
                        r["service_id"],
                        nullable(r.get("trip_headsign", "")),
                        integer(r.get("direction_id", "")),
                        nullable(r.get("shape_id", "")),
                    )
                    for r in rows(archive, "trips.txt")
                ),
            )
            trip_keys = dict(connection.execute("SELECT trip_id,trip_pk FROM trips"))
            load(
                "stop_times",
                "INSERT INTO stop_times VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    (
                        trip_keys[r["trip_id"]],
                        int(r["stop_sequence"]),
                        r["stop_id"],
                        gtfs_seconds(r.get("arrival_time", "")),
                        gtfs_seconds(r.get("departure_time", "")),
                        integer(r.get("pickup_type", ""), 0),
                        integer(r.get("drop_off_type", ""), 0),
                        integer(r.get("timepoint", "")),
                        number(r.get("shape_dist_traveled", "")),
                    )
                    for r in rows(archive, "stop_times.txt")
                ),
            )
            load(
                "shape_points",
                "INSERT INTO shape_points VALUES (?,?,?,?,?)",
                (
                    (
                        r["shape_id"],
                        int(r["shape_pt_sequence"]),
                        float(r["shape_pt_lat"]),
                        float(r["shape_pt_lon"]),
                        number(r.get("shape_dist_traveled", "")),
                    )
                    for r in rows(archive, "shapes.txt")
                ),
            )
            connection.execute("INSERT INTO shapes SELECT DISTINCT shape_id FROM shape_points")
            load(
                "frequencies",
                "INSERT INTO frequencies VALUES (?,?,?,?,?)",
                (
                    (
                        trip_keys[r["trip_id"]],
                        gtfs_seconds(r["start_time"]),
                        gtfs_seconds(r["end_time"]),
                        int(r["headway_secs"]),
                        integer(r.get("exact_times", ""), 0),
                    )
                    for r in rows(archive, "frequencies.txt")
                ),
            )
            load(
                "feed_info",
                "INSERT INTO feed_info VALUES (?)",
                ((json.dumps(r, ensure_ascii=False),) for r in rows(archive, "feed_info.txt")),
            )
            step = time.perf_counter()
            counts["patterns"] = _patterns(connection)
            timings["patterns"] = time.perf_counter() - step
            if connection.execute(
                "SELECT 1 FROM trips WHERE pattern_id IS NULL LIMIT 1"
            ).fetchone():
                raise CatalogError("A trip has no stop sequence")
            if not all(counts.get(t) for t in ("routes", "stops", "trips", "stop_times")):
                raise CatalogError("Empty required GTFS table")
        step = time.perf_counter()
        connection.executescript(INDEXES)
        connection.execute("ANALYZE")
        timings["indexes"] = time.perf_counter() - step
        if connection.execute("PRAGMA foreign_key_check").fetchone():
            raise CatalogError("GTFS contains an orphan reference")
        if connection.execute("SELECT 1 FROM frequencies WHERE start>=end LIMIT 1").fetchone():
            raise CatalogError("Invalid frequency window")
        if file_hash(zip_path) != sha:
            raise CatalogError("ZIP changed during import")
        timings["total_seconds"] = time.perf_counter() - started
        connection.execute(
            "INSERT INTO catalog_versions VALUES (?,?,?,?,?,?,?,?,?)",
            (
                sha,
                str(zip_path),
                source_url,
                datetime.now(BOGOTA).isoformat(),
                zip_path.stat().st_size,
                batch_size,
                json.dumps(counts),
                json.dumps(timings),
                SCHEMA_VERSION,
            ),
        )
        connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        connection.commit()
        connection.close()
        connection = None
        if database.exists():
            raise CatalogError("Destination appeared during import; refusing to overwrite it")
        staging.rename(database)
        return {
            "status": "imported",
            "sha256": sha,
            "database": str(database),
            "database_bytes": database.stat().st_size,
            "elapsed_seconds": time.perf_counter() - started,
            "counts": counts,
            "timings": timings,
        }
    except (sqlite3.Error, BadZipFile, OSError, ValueError, KeyError, csv.Error) as exc:
        raise CatalogError(f"Import failed: {exc}") from exc
    finally:
        if connection is not None:
            connection.close()
        if staging.exists():
            staging.unlink()
        journal = Path(str(staging) + "-journal")
        if journal.exists():
            journal.unlink()
