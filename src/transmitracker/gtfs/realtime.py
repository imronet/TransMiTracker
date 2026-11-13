"""Decode GTFS-RT, keeping absent fields distinct from zero/default values."""

import math
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2 as pb

from transmitracker.gtfs import FeedError

BOGOTA = ZoneInfo("America/Bogota")


def field(message, name):
    return getattr(message, name) if message.HasField(name) else None


def timestamp_info(timestamp: int | None, now: datetime, max_age: int = 300) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if timestamp is None:
        return {"timestamp": None, "at_bogota": None, "age_seconds": None, "freshness": "unknown"}
    try:
        date = datetime.fromtimestamp(timestamp, BOGOTA)
    except (OverflowError, OSError, ValueError) as exc:
        raise FeedError("Timestamp out of supported range") from exc
    age = now.timestamp() - timestamp
    freshness = "future" if age < -60 else "stale" if age > max_age else "recent"
    return {
        "timestamp": timestamp,
        "at_bogota": date.isoformat(),
        "age_seconds": round(age, 3),
        "freshness": freshness,
    }


def decode_realtime(payload: bytes):
    feed = pb.FeedMessage()
    try:
        feed.ParseFromString(payload)
    except DecodeError as exc:
        raise FeedError("Invalid GTFS Realtime Protobuf") from exc
    if not feed.IsInitialized():
        raise FeedError(f"Missing required Protobuf fields: {feed.FindInitializationErrors()}")
    if feed.header.gtfs_realtime_version not in {"1.0", "2.0"}:
        raise FeedError("Unsupported GTFS Realtime version")
    identities = [entity.id for entity in feed.entity]
    if any(not identity for identity in identities) or len(identities) != len(set(identities)):
        raise FeedError("Empty or duplicate entity IDs")
    for entity in feed.entity:
        if entity.HasField("vehicle") and entity.vehicle.HasField("position"):
            position = entity.vehicle.position
            if not (
                math.isfinite(position.latitude)
                and math.isfinite(position.longitude)
                and -90 <= position.latitude <= 90
                and -180 <= position.longitude <= 180
            ):
                raise FeedError(f"Invalid coordinates for entity {entity.id}")
    return feed


def observations(feed, *, now: datetime) -> list[dict]:
    records = []
    for entity in feed.entity:
        if not entity.HasField("vehicle") or entity.is_deleted:
            continue
        vehicle = entity.vehicle
        trip = vehicle.trip
        records.append(
            {
                "entity_id": entity.id,
                "vehicle_id": field(vehicle.vehicle, "id"),
                "trip_id": field(trip, "trip_id"),
                "route_id": field(trip, "route_id"),
                "direction_id": field(trip, "direction_id"),
                "start_date": field(trip, "start_date"),
                "start_time": field(trip, "start_time"),
                "stop_id": field(vehicle, "stop_id"),
                "current_stop_sequence": field(vehicle, "current_stop_sequence"),
                "current_status": pb.VehiclePosition.VehicleStopStatus.Name(vehicle.current_status),
                "latitude": field(vehicle.position, "latitude"),
                "longitude": field(vehicle.position, "longitude"),
                "reported": timestamp_info(field(vehicle, "timestamp"), now),
            }
        )
    return records


def summarize_realtime(feed, *, now: datetime) -> dict:
    vehicles = observations(feed, now=now)
    kinds = Counter()
    update_freshness = Counter()
    stop_update_count = 0
    updates_with_stops = 0
    trip_updates, alerts = [], []
    for entity in feed.entity:
        if entity.is_deleted:
            kinds["deleted"] += 1
            continue
        for kind in ("vehicle", "trip_update", "alert", "shape", "stop", "trip_modifications"):
            if kind in entity.DESCRIPTOR.fields_by_name and entity.HasField(kind):
                kinds[kind] += 1
        if entity.HasField("trip_update"):
            update = entity.trip_update
            update_freshness[timestamp_info(field(update, "timestamp"), now)["freshness"]] += 1
            stop_update_count += len(update.stop_time_update)
            updates_with_stops += bool(update.stop_time_update)
        if entity.HasField("trip_update") and len(trip_updates) < 3:
            update = entity.trip_update
            trip_updates.append(
                {
                    "entity_id": entity.id,
                    "trip_id": field(update.trip, "trip_id"),
                    "route_id": field(update.trip, "route_id"),
                    "vehicle_id": field(update.vehicle, "id"),
                    "reported": timestamp_info(field(update, "timestamp"), now),
                    "stop_time_update_count": len(update.stop_time_update),
                    "stops": [
                        {
                            "stop_id": field(s, "stop_id"),
                            "stop_sequence": field(s, "stop_sequence"),
                            "arrival_time": field(s.arrival, "time"),
                            "departure_time": field(s.departure, "time"),
                        }
                        for s in update.stop_time_update[:3]
                    ],
                }
            )
        if entity.HasField("alert") and len(alerts) < 3:
            alert = entity.alert
            alerts.append(
                {
                    "entity_id": entity.id,
                    "headers": [t.text for t in alert.header_text.translation],
                    "selectors": [
                        {
                            "route_id": field(s, "route_id"),
                            "stop_id": field(s, "stop_id"),
                            "trip_id": field(s.trip, "trip_id"),
                        }
                        for s in alert.informed_entity
                    ],
                }
            )
    return {
        "validation_scope": "protobuf_required_fields_version_ids_and_vehicle_coordinates",
        "gtfs_realtime_version": feed.header.gtfs_realtime_version,
        "incrementality": pb.FeedHeader.Incrementality.Name(feed.header.incrementality),
        "header": timestamp_info(field(feed.header, "timestamp"), now),
        "entity_count": len(feed.entity),
        "entities_by_kind": dict(kinds),
        "vehicle_freshness": dict(Counter(v["reported"]["freshness"] for v in vehicles)),
        "trip_update_freshness": dict(update_freshness),
        "stop_time_update_count": stop_update_count,
        "trip_updates_with_stops": updates_with_stops,
        "vehicle_fields_present": {
            key: sum(v[key] is not None for v in vehicles)
            for key in ("vehicle_id", "trip_id", "route_id", "stop_id", "latitude", "longitude")
        },
        "vehicle_samples": vehicles[:3],
        "trip_update_samples": trip_updates,
        "alert_samples": alerts,
        "warnings": [
            "Differential feed requires previous state; this reader does not reconstruct it."
        ]
        if feed.header.incrementality == pb.FeedHeader.DIFFERENTIAL
        else [],
    }


def is_recent_snapshot(summary: dict) -> bool:
    """Connectivity/freshness evidence only; not an assurance of usable ETAs."""
    kinds = summary["entities_by_kind"]
    return bool(
        summary["header"]["freshness"] == "recent"
        and summary["entity_count"]
        and summary["incrementality"] == "FULL_DATASET"
        and (not kinds.get("vehicle") or summary["vehicle_freshness"].get("recent", 0))
        and (not kinds.get("trip_update") or summary["trip_update_freshness"].get("recent", 0))
    )
