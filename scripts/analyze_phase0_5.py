"""Analyze original real captures, static versions and offline snapshot storage."""

import csv
import gzip
import io
import json
import math
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
from zoneinfo import ZoneInfo

from google.protobuf.json_format import MessageToDict

from transmitracker.gtfs.realtime import decode_realtime, observations
from transmitracker.research.snapshots import SCHEMA, digest, encoded, ingest_snapshot

ROOT = Path(__file__).resolve().parents[1]
BOGOTA = ZoneInfo("America/Bogota")


def csv_rows(archive, name):
    with (
        archive.open(name) as raw,
        io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream,
    ):
        yield from csv.DictReader(stream)


def read_core(path):
    with ZipFile(path) as archive:
        result = {
            name: list(csv_rows(archive, name))
            for name in (
                "routes.txt",
                "trips.txt",
                "calendar.txt",
                "calendar_dates.txt",
                "feed_info.txt",
                "frequencies.txt",
            )
            if name in archive.namelist()
        }
        result["files"] = archive.namelist()
        result["stops"] = {r["stop_id"] for r in csv_rows(archive, "stops.txt")}
    result["routes"] = {row["route_id"]: row for row in result["routes.txt"]}
    result["trips"] = {row["trip_id"]: row for row in result["trips.txt"]}
    return result


def presence(message, prefix=""):
    fields = []
    for descriptor, value in message.ListFields():
        name = prefix + descriptor.name
        fields.append(name)
        if descriptor.message_type is not None and not descriptor.is_repeated:
            fields.extend(presence(value, name + "."))
    return fields


def temporal(messages, query):
    messages = list(messages)
    timestamps = [m.timestamp for m in messages if m.HasField("timestamp")]
    dates = Counter(datetime.fromtimestamp(t, BOGOTA).date().isoformat() for t in timestamps)
    ages = sorted(query.timestamp() - t for t in timestamps)
    bins = Counter()
    for age in ages:
        label = (
            "future_gt_60s"
            if age < -60
            else "0_to_5m"
            if age <= 300
            else "5_to_30m"
            if age <= 1800
            else "30m_to_2h"
            if age <= 7200
            else "2_to_6h"
            if age <= 21600
            else "6_to_24h"
            if age <= 86400
            else "1_to_7d"
            if age <= 604800
            else "over_7d"
        )
        bins[label] += 1
    old = [m for m in messages if m.HasField("timestamp") and query.timestamp() - m.timestamp > 300]
    raw_samples = [
        MessageToDict(m, preserving_proto_field_name=True)
        for m in sorted(old, key=lambda m: m.timestamp)[:3]
    ]
    for sample in raw_samples:
        if "vehicle" in sample:
            sample["vehicle"].pop("license_plate", None)
            sample["vehicle"].pop("label", None)
    return {
        "reference_query_at": query.isoformat(),
        "total": len(messages),
        "timestamp_present": len(timestamps),
        "timestamp_missing": len(messages) - len(timestamps),
        "min_at": datetime.fromtimestamp(min(timestamps), BOGOTA).isoformat()
        if timestamps
        else None,
        "max_at": datetime.fromtimestamp(max(timestamps), BOGOTA).isoformat()
        if timestamps
        else None,
        "local_dates": dict(sorted(dates.items())),
        "age_bins": dict(bins),
        "age_seconds_quantiles": {
            str(p): ages[min(len(ages) - 1, math.floor((len(ages) - 1) * p))]
            for p in (0, 0.25, 0.5, 0.75, 0.95, 0.99, 1)
        }
        if ages
        else {},
        "all_field_presence": dict(Counter(f for m in messages for f in presence(m))),
        "old_field_presence": dict(Counter(f for m in old for f in presence(m))),
        "oldest_raw_samples": raw_samples,
        "schedule_relationships": dict(
            Counter(str(m.trip.schedule_relationship) for m in messages)
        ),
    }


def active_services(core, day):
    service_date = datetime.strptime(day, "%Y%m%d").date()
    weekday = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")[
        service_date.weekday()
    ]
    active = {
        row["service_id"]
        for row in core.get("calendar.txt", [])
        if row["start_date"] <= day <= row["end_date"] and row[weekday] == "1"
    }
    for row in core.get("calendar_dates.txt", []):
        if row["date"] == day:
            if row["exception_type"] == "1":
                active.add(row["service_id"])
            elif row["exception_type"] == "2":
                active.discard(row["service_id"])
    return active


def compare_ids(core, records, updates):
    counts = Counter()
    examples = {}
    active_cache = {}
    for record in records:
        trip = core["trips"].get(record["trip_id"])
        status = (
            "consistent"
            if trip and trip["route_id"] == record["route_id"]
            else "route_conflict"
            if trip
            else "missing_trip"
        )
        counts[status] += 1
        counts["route_found"] += record["route_id"] in core["routes"]
        counts["stop_found"] += record["stop_id"] in core["stops"]
        if trip and record["start_date"]:
            day = record["start_date"]
            if day not in active_cache:
                active_cache[day] = active_services(core, day)
            counts[f"{status}_service_active"] += trip["service_id"] in active_cache[day]
        if status not in examples:
            examples[status] = {**record, "static_trip": trip}
    update_counts = Counter()
    for update in updates:
        trip = core["trips"].get(update.trip.trip_id)
        update_counts["trip_found"] += trip is not None
        update_counts["route_found"] += update.trip.route_id in core["routes"]
        update_counts["route_conflict"] += bool(trip and trip["route_id"] != update.trip.route_id)
    return {
        "positions": dict(counts),
        "trip_updates": dict(update_counts),
        "examples": examples,
        "static_counts": {
            "trips": len(core["trips"]),
            "routes": len(core["routes"]),
            "stops": len(core["stops"]),
        },
        "feed_info": core.get("feed_info.txt"),
        "active_services_by_date": {k: sorted(v) for k, v in active_cache.items()},
    }


def main():
    output = ROOT / "data/phase0_5"
    output.mkdir(parents=True, exist_ok=True)
    original = json.loads((ROOT / "docs/LIVE_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    entries = {e["name"]: e for e in original["results"]}
    paths = {
        "positions": ROOT / "data/probes/official_positions.pb",
        "tripupdates": ROOT / "data/probes/official_tripupdates.pb",
        "static": ROOT / "data/probes/official_static.zip",
    }
    real = {}
    for name, path in paths.items():
        actual = sha256(path.read_bytes()).hexdigest()
        expected = entries["official_" + name]["download"]["sha256"]
        if actual != expected:
            raise ValueError(f"Original evidence changed: {name}")
        real[name] = {
            "file": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "sha256": actual,
        }
    positions = decode_realtime(paths["positions"].read_bytes())
    tripupdates = decode_realtime(paths["tripupdates"].read_bytes())
    query = datetime.fromisoformat(entries["official_positions"]["download"]["queried_at"])
    records = observations(positions, now=query)
    updates = [e.trip_update for e in tripupdates.entity if e.HasField("trip_update")]
    core = read_core(paths["static"])
    report = {
        "mode": "offline_analysis_of_original_real_captures",
        "network_requests": 0,
        "analyzed_at": datetime.now(BOGOTA).isoformat(),
        "evidence": real,
        "positions_temporal": temporal(
            [e.vehicle for e in positions.entity if e.HasField("vehicle")], query
        ),
        "tripupdates_temporal": temporal(
            updates,
            datetime.fromisoformat(entries["official_tripupdates"]["download"]["queried_at"]),
        ),
        "headers": {
            name: MessageToDict(feed.header, preserving_proto_field_name=True)
            for name, feed in (("positions", positions), ("tripupdates", tripupdates))
        },
        "static_versions": {"original_20261112": compare_ids(core, records, updates)},
    }
    historical = output / "GTFS_20261027.zip"
    if historical.exists():
        previous = read_core(historical)
        report["static_versions"]["archive_20261027"] = compare_ids(previous, records, updates)
        report["historical_static_evidence"] = {
            "bytes": historical.stat().st_size,
            "sha256": sha256(historical.read_bytes()).hexdigest(),
            "files": previous["files"],
            "classification": "static_schedule_not_operational_history",
        }
        common = core["trips"].keys() & previous["trips"].keys()
        report["static_version_differences"] = {
            "common_trip_ids": len(common),
            "common_trip_ids_with_different_route": sum(
                core["trips"][key]["route_id"] != previous["trips"][key]["route_id"]
                for key in common
            ),
        }
    by_trip = defaultdict(list)
    for update in updates:
        by_trip[update.trip.trip_id].append(update)
    cross = Counter()
    for record in records:
        candidates = by_trip.get(record["trip_id"], [])
        cross["ambiguous_trip_id_in_tripupdates"] += len(candidates) > 1
        update = candidates[0] if len(candidates) == 1 else None
        cross["same_trip_id_in_tripupdates"] += update is not None
        if update:
            cross["same_trip_different_route"] += record["route_id"] != update.trip.route_id
            cross["same_trip_same_vehicle"] += record["vehicle_id"] == update.vehicle.id
            cross["same_trip_different_start_date"] += (
                record["start_date"] != update.trip.start_date
            )
            cross["same_trip_different_start_time"] += (
                record["start_time"] != update.trip.start_time
            )
    report["crossfeed_exact_trip_comparison"] = dict(cross)
    report["tripupdate_duplicate_trip_ids"] = sum(len(values) > 1 for values in by_trip.values())
    report["producer_field_diagnostics"] = {
        "position_start_time_equals_observation_local_time": sum(
            r["start_time"]
            == datetime.fromtimestamp(r["reported"]["timestamp"], BOGOTA).strftime("%H:%M:%S")
            for r in records
            if r["reported"]["timestamp"] is not None
        ),
        "position_start_date_equals_observation_local_date": sum(
            r["start_date"]
            == datetime.fromtimestamp(r["reported"]["timestamp"], BOGOTA).strftime("%Y%m%d")
            for r in records
            if r["reported"]["timestamp"] is not None
        ),
        "position_trip_id_suffix_equals_route_id": sum(
            (r["trip_id"] or "").rsplit(".", 1)[-1] == r["route_id"] for r in records
        ),
        "static_trip_id_suffix_equals_route_id": sum(
            key.rsplit(".", 1)[-1] == value["route_id"] for key, value in core["trips"].items()
        ),
        "tripupdate_delay_summary": {
            "present": sum(u.HasField("delay") for u in updates),
            "zero": sum(u.HasField("delay") and u.delay == 0 for u in updates),
            "positive": sum(u.HasField("delay") and u.delay > 0 for u in updates),
            "negative": sum(u.HasField("delay") and u.delay < 0 for u in updates),
            "min": min(u.delay for u in updates if u.HasField("delay")),
            "max": max(u.delay for u in updates if u.HasField("delay")),
        },
        "scheduled_updates_without_stop_time_update": sum(
            u.trip.schedule_relationship == 0 and not u.stop_time_update for u in updates
        ),
        "position_start_dates": dict(Counter(r["start_date"] for r in records)),
        "tripupdate_start_dates": dict(Counter(u.trip.start_date for u in updates)),
    }
    report["stop_time_update_count"] = sum(len(u.stop_time_update) for u in updates)
    payload = paths["positions"].read_bytes()
    sizes = {
        "positions_full_pb": len(payload),
        "positions_full_gzip": len(gzip.compress(payload, mtime=0)),
        "tripupdates_full_pb": paths["tripupdates"].stat().st_size,
    }
    selected_route = "11836"  # Explicit illustrative real K721 route, not a user profile.
    selected = [r for r in records if r["route_id"] == selected_route]
    sizes["illustrative_route_id"] = selected_route
    sizes["selected_vehicle_count"] = len(selected)
    sizes["route_filtered_before_quality_jsonl_bytes"] = len(
        ("\n".join(encoded(r) for r in selected) + "\n").encode("utf-8")
    )
    accepted = [
        r
        for r in selected
        if r["reported"]["freshness"] == "recent"
        and all(
            r.get(key) for key in ("vehicle_id", "trip_id", "start_date", "start_time", "route_id")
        )
    ]
    sizes["filtered_jsonl_bytes"] = len(
        ("\n".join(encoded(r) for r in accepted) + "\n").encode("utf-8")
    )
    database = output / "real_replay.sqlite3"
    # Each run gets a new local experiment file; never truncates an existing DB.
    if database.exists():
        database = output / (
            "real_replay_" + datetime.now(BOGOTA).strftime("%H%M%S%f") + ".sqlite3"
        )
    with sqlite3.connect(database) as connection:
        first = ingest_snapshot(
            connection,
            payload,
            provider="official-tmsa",
            captured_at=query,
            route_ids={selected_route},
            catalog_sha256=real["static"]["sha256"],
        )
        duplicate = ingest_snapshot(
            connection,
            payload,
            provider="official-tmsa",
            captured_at=query,
            route_ids={selected_route},
            catalog_sha256=real["static"]["sha256"],
        )
        count = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
        pages = connection.execute("PRAGMA page_count").fetchone()[0]
    sizes.update(
        sqlite_total_bytes=database.stat().st_size,
        sqlite_page_size=page_size,
        sqlite_pages=pages,
        persisted_observations=count,
    )
    # Measure steady schema growth using actual rows from this real snapshot.
    with sqlite3.connect(database) as source, sqlite3.connect(":memory:") as expanded:
        source.backup(expanded)
        base_bytes = expanded.execute("PRAGMA page_count").fetchone()[0] * page_size
        columns = "journey_id,observed_at,snapshot_id,latitude,longitude,stop_id,stop_sequence,stop_status,fingerprint,mapping_status"
        for step in range(1, 201):
            expanded.execute(
                f"INSERT INTO observations ({columns}) SELECT journey_id,observed_at+?,snapshot_id,latitude,longitude,stop_id,stop_sequence,stop_status,fingerprint,mapping_status FROM observations WHERE snapshot_id=? AND observed_at IN (SELECT observed_at FROM observations WHERE snapshot_id=? ORDER BY observed_at LIMIT ?)",
                (
                    step * 100000,
                    source.execute("SELECT id FROM snapshots LIMIT 1").fetchone()[0],
                    source.execute("SELECT id FROM snapshots LIMIT 1").fetchone()[0],
                    count,
                ),
            )
        expanded.commit()
        total_count = expanded.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        total_bytes = expanded.execute("PRAGMA page_count").fetchone()[0] * page_size
    sizes["sqlite_synthetic_growth_benchmark"] = {
        "origin": "synthetic_timestamp_replication_of_real_row_shapes_not_real_movement",
        "base_rows": count,
        "expanded_rows": total_count,
        "delta_bytes": total_bytes - base_bytes,
        "bytes_per_additional_observation": (total_bytes - base_bytes) / (total_count - count)
        if total_count > count
        else None,
    }
    with sqlite3.connect(":memory:") as metadata_db:
        metadata_db.executescript(SCHEMA)
        initial = metadata_db.execute("PRAGMA page_count").fetchone()[0] * page_size
        for index in range(1000):
            metadata_db.execute(
                "INSERT INTO snapshots VALUES (?,?,?,?,?,?,?)",
                (
                    digest(index),
                    "official-tmsa",
                    query.isoformat(),
                    positions.header.timestamp,
                    real["positions"]["sha256"],
                    real["static"]["sha256"],
                    encoded(first),
                ),
            )
        metadata_db.commit()
        grown = metadata_db.execute("PRAGMA page_count").fetchone()[0] * page_size
    sizes["sqlite_metadata_bytes_per_snapshot_benchmark"] = (grown - initial) / 1000
    with sqlite3.connect(database) as source, sqlite3.connect(":memory:") as churn:
        source.backup(churn)
        initial = churn.execute("PRAGMA page_count").fetchone()[0] * page_size
        rows = source.execute(
            "SELECT o.*,j.identity_json FROM observations o JOIN journeys j ON j.id=o.journey_id"
        ).fetchall()
        for generation in range(1, 201):
            for row in rows:
                new_identity = json.loads(row[-1])
                new_identity[4] = f"{generation // 60:02}:{generation % 60:02}:00"
                key = digest(new_identity)
                churn.execute("INSERT INTO journeys VALUES (?,?)", (key, encoded(new_identity)))
                churn.execute(
                    "INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (key, row[1] + generation * 100000, *row[2:-1]),
                )
        churn.commit()
        grown = churn.execute("PRAGMA page_count").fetchone()[0] * page_size
    sizes["sqlite_identity_churn_bytes_per_new_observation_benchmark"] = (
        (grown - initial) / (count * 200) if count else None
    )
    report["real_offline_replay"] = {
        "origin": "one_saved_real_snapshot_replayed_twice_not_two_temporal_captures",
        "first": first,
        "repeated": duplicate,
        "database": database.relative_to(ROOT).as_posix(),
        "event_reconstruction_demonstrated": False,
    }
    report["storage_measurements"] = sizes
    report["storage_projections"] = [
        {
            "interval_seconds": interval,
            "requests_per_24h": 86400 // interval,
            "positions_full_bytes_per_day": len(payload) * (86400 // interval),
            "positions_full_gzip_bytes_per_day": sizes["positions_full_gzip"] * (86400 // interval),
            "tripupdates_full_bytes_per_day": sizes["tripupdates_full_pb"] * (86400 // interval),
            "filtered_jsonl_bytes_per_day": sizes["filtered_jsonl_bytes"] * (86400 // interval),
            "filtered_sqlite_stable_identity_bytes_per_day": (
                sizes["sqlite_synthetic_growth_benchmark"]["bytes_per_additional_observation"]
                * count
                + sizes["sqlite_metadata_bytes_per_snapshot_benchmark"]
            )
            * (86400 // interval)
            if count
            else None,
            "filtered_sqlite_identity_churn_bytes_per_day": (
                sizes["sqlite_identity_churn_bytes_per_new_observation_benchmark"] * count
                + sizes["sqlite_metadata_bytes_per_snapshot_benchmark"]
            )
            * (86400 // interval)
            if count
            else None,
        }
        for interval in (40, 60, 120)
    ]
    (ROOT / "docs/PHASE0_5_ANALYSIS.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    for name in ("positions_temporal", "tripupdates_temporal"):
        print(name, report[name]["min_at"], report[name]["max_at"], report[name]["age_bins"])
    for name, result in report["static_versions"].items():
        print(name, result["positions"])
    print("Crossfeed:", report["crossfeed_exact_trip_comparison"])
    print("Storage:", sizes)


if __name__ == "__main__":
    main()
