"""Offline multi-vehicle snapshot ingestion prototype. No networking or timer."""

import hashlib
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime

from transmitracker.gtfs import FeedError
from transmitracker.gtfs.realtime import decode_realtime, observations, timestamp_info

SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY, provider TEXT NOT NULL, captured_at TEXT NOT NULL,
    header_timestamp INTEGER, payload_sha256 TEXT NOT NULL, catalog_sha256 TEXT,
    counts_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS journeys (
    id TEXT PRIMARY KEY, identity_json TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS observations (
    journey_id TEXT NOT NULL REFERENCES journeys(id), observed_at INTEGER NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id), latitude REAL NOT NULL,
    longitude REAL NOT NULL, stop_id TEXT, stop_sequence INTEGER, stop_status TEXT,
    fingerprint TEXT NOT NULL, mapping_status TEXT NOT NULL DEFAULT 'unresolved',
    PRIMARY KEY(journey_id, observed_at)
);
"""


def identity(record: dict, provider: str) -> tuple:
    """Conservative identity: never infer service date from the capture date.

    Route/direction changes split the candidate journey. Catalog hashes belong
    to provenance, not this identity. Grouping does not validate the producer's
    trip/route association. Missing start_time is quarantined in this experiment.
    """
    required = ("vehicle_id", "trip_id", "start_date", "start_time", "route_id")
    if not provider or any(not record.get(key) for key in required):
        raise ValueError("incomplete_identity")
    service_date = record["start_date"]
    if not re.fullmatch(r"\d{8}", service_date):
        raise ValueError("invalid_service_date")
    datetime.strptime(service_date, "%Y%m%d")
    start = record["start_time"]
    if not re.fullmatch(r"\d{2,}:\d{2}:\d{2}", start) or any(
        int(x) > 59 for x in start.split(":")[1:]
    ):
        raise ValueError("invalid_start_time")
    return (
        provider,
        record["vehicle_id"],
        record["trip_id"],
        service_date,
        start,
        record["route_id"],
        record.get("direction_id"),
        record.get("schedule_relationship", 0),
    )


def encoded(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(value) -> str:
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def ingest_snapshot(
    connection: sqlite3.Connection,
    payload: bytes,
    *,
    provider: str,
    captured_at: datetime,
    route_ids: set[str],
    catalog_sha256: str | None = None,
) -> dict:
    """Process one explicitly supplied snapshot transactionally; no arrival inference.

    Same observation identity/time/content is idempotent. Different content at
    the same identity/time is counted as a conflict and never overwrites data.
    Older observations are quarantined rather than advancing a trajectory.
    The caller owns this research-only SQLite database and its lifecycle.
    """
    if not route_ids:
        raise ValueError("An explicit nonempty route filter is required")
    if captured_at.tzinfo is None or captured_at.utcoffset() is None:
        raise ValueError("captured_at must be timezone-aware")
    feed = decode_realtime(payload)
    if feed.header.incrementality != 0:
        raise FeedError("Offline experiment accepts FULL_DATASET only")
    header_ts = feed.header.timestamp if feed.header.HasField("timestamp") else None
    payload_sha = hashlib.sha256(payload).hexdigest()
    snapshot_id = digest([provider, captured_at.isoformat(), payload_sha])
    connection.executescript(SCHEMA)
    previous = connection.execute(
        "SELECT counts_json FROM snapshots WHERE id=?", (snapshot_id,)
    ).fetchone()
    if previous:
        return {"replayed_snapshot": True, "inserted": 0}
    counts = Counter()
    with connection:
        connection.execute(
            "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?)",
            (
                snapshot_id,
                provider,
                captured_at.isoformat(),
                header_ts,
                payload_sha,
                catalog_sha256,
                "{}",
            ),
        )
        if timestamp_info(header_ts, captured_at)["freshness"] != "recent":
            counts["rejected_header"] += 1
        else:
            records = observations(feed, now=captured_at)
            relationships = {
                entity.id: entity.vehicle.trip.schedule_relationship
                for entity in feed.entity
                if entity.HasField("vehicle")
            }
            for record in records:
                counts["seen"] += 1
                if record["route_id"] not in route_ids:
                    counts["filtered_out"] += 1
                    continue
                if record["reported"]["freshness"] != "recent":
                    counts["rejected_timestamp"] += 1
                    continue
                if record["latitude"] is None or record["longitude"] is None:
                    counts["rejected_position"] += 1
                    continue
                record["schedule_relationship"] = relationships[record["entity_id"]]
                try:
                    journey_identity = identity(record, provider)
                except ValueError:
                    counts["quarantined_identity"] += 1
                    continue
                journey_id = digest(journey_identity)
                observed_at = record["reported"]["timestamp"]
                content = [
                    record[key]
                    for key in (
                        "latitude",
                        "longitude",
                        "stop_id",
                        "current_stop_sequence",
                        "current_status",
                    )
                ]
                fingerprint = digest(content)
                previous = connection.execute(
                    "SELECT fingerprint FROM observations WHERE journey_id=? AND observed_at=?",
                    (journey_id, observed_at),
                ).fetchone()
                if previous:
                    counts["duplicate" if previous[0] == fingerprint else "timestamp_conflict"] += 1
                    continue
                latest = connection.execute(
                    "SELECT MAX(observed_at) FROM observations WHERE journey_id=?", (journey_id,)
                ).fetchone()[0]
                if latest is not None and observed_at < latest:
                    counts["quarantined_out_of_order"] += 1
                    continue
                connection.execute(
                    "INSERT OR IGNORE INTO journeys VALUES (?,?)",
                    (journey_id, encoded(journey_identity)),
                )
                connection.execute(
                    "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (journey_id, observed_at, snapshot_id, *content, fingerprint, "unresolved"),
                )
                counts["inserted"] += 1
        connection.execute(
            "UPDATE snapshots SET counts_json=? WHERE id=?", (encoded(counts), snapshot_id)
        )
    return dict(counts)
