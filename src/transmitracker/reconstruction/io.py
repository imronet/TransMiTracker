"""Local snapshot adapters only. Never import a downloader or create an HTTP client."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from google.protobuf.json_format import MessageToDict

from transmitracker.gtfs.realtime import decode_realtime, field
from transmitracker.reconstruction.models import (
    OriginalObservation,
    ProviderSnapshot,
    canonical,
    digest,
)


def epoch(value):
    if value is None:
        return None
    if type(value) in (int, float):
        return float(value)
    when = datetime.fromisoformat(value)
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("Timestamps must include timezone")
    return when.timestamp()


def snapshot_from_rows(
    *,
    source,
    endpoint,
    catalog_sha256,
    origin,
    rows,
    feed_as_of=None,
    received_at=None,
    receipt_reference_at=None,
    payload_sha256=None,
    complete=True,
    provenance=None,
):
    if origin not in ("synthetic_fixture", "saved_real_snapshot"):
        raise ValueError("Only explicit offline origins are supported")
    raw = canonical(rows)
    payload_sha256 = payload_sha256 or hashlib.sha256(raw.encode()).hexdigest()
    header = {
        "source": source,
        "endpoint": endpoint,
        "origin": origin,
        "catalog_sha256": catalog_sha256,
        "payload_sha256": payload_sha256,
        "feed_as_of": epoch(feed_as_of),
        "received_at": epoch(received_at),
        "receipt_reference_at": epoch(receipt_reference_at),
        "complete": complete,
    }
    observations = []
    for row in rows:

        def number(key, row=row):
            value = row.get(key)
            return float(value) if type(value) in (int, float) else None

        def identity(key, row=row):
            value = row.get(key)
            if value is not None and not isinstance(value, str):
                raise ValueError("Identifiers must remain original strings")
            return value

        observation_id = digest((source, endpoint, row))
        observations.append(
            OriginalObservation(
                observation_id,
                source,
                endpoint,
                identity("entity_id"),
                identity("vehicle_id"),
                identity("trip_id"),
                identity("route_id"),
                identity("start_date"),
                identity("start_time"),
                row.get("direction_id"),
                number("reported_at"),
                number("latitude"),
                number("longitude"),
                identity("stop_id"),
                row.get("current_stop_sequence"),
                row.get("current_status"),
                canonical(row),
                row.get("position_kind", "observed"),
            )
        )
    return ProviderSnapshot(
        digest((header, raw)),
        **header,
        observations=tuple(observations),
        provenance_json=canonical(provenance or {}),
    )


def read_saved_capture(path: Path, catalog_sha256):
    path = Path(path).resolve()
    record = json.loads(path.read_text(encoding="utf-8"))
    if record["origin"] not in ("saved_real_snapshot", "real_network_capture", "synthetic_fixture"):
        raise ValueError("Unknown capture origin")
    raw_path = (path.parent / record["raw_file"]).resolve()
    if not raw_path.is_relative_to(path.parent):
        raise ValueError("Capture file must remain within evidence directory")
    payload = raw_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != record["payload_sha256"]:
        raise ValueError("Saved capture hash mismatch")
    feed = decode_realtime(payload)
    if feed.header.incrementality != 0:
        raise ValueError("Only complete snapshots supported")
    rows = []
    for entity in feed.entity:
        if not entity.HasField("vehicle") or entity.is_deleted:
            continue
        vehicle, trip = entity.vehicle, entity.vehicle.trip
        rows.append(
            {
                "entity_id": entity.id,
                "vehicle_id": field(vehicle.vehicle, "id"),
                "trip_id": field(trip, "trip_id"),
                "route_id": field(trip, "route_id"),
                "start_date": field(trip, "start_date"),
                "start_time": field(trip, "start_time"),
                "direction_id": field(trip, "direction_id"),
                "reported_at": field(vehicle, "timestamp"),
                "latitude": field(vehicle.position, "latitude"),
                "longitude": field(vehicle.position, "longitude"),
                "stop_id": field(vehicle, "stop_id"),
                "current_stop_sequence": field(vehicle, "current_stop_sequence"),
                "current_status": vehicle.VehicleStopStatus.Name(vehicle.current_status)
                if vehicle.HasField("current_status")
                else None,
                "protobuf_vehicle": MessageToDict(vehicle, preserving_proto_field_name=True),
            }
        )
    verified = record.get("receipt_timestamp_verified", False)
    return snapshot_from_rows(
        source=record["source"],
        endpoint=record["source"],
        catalog_sha256=catalog_sha256,
        origin="synthetic_fixture"
        if record["origin"] == "synthetic_fixture"
        else "saved_real_snapshot",
        rows=rows,
        feed_as_of=field(feed.header, "timestamp"),
        received_at=record["received_at"] if verified else None,
        receipt_reference_at=None if verified else record["received_at"],
        payload_sha256=record["payload_sha256"],
        provenance={
            "capture_path": str(path),
            "raw_path": str(raw_path),
            "capture_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "receipt_timestamp_verified": verified,
            "original_reference_kind": record.get("reference_time_kind"),
        },
    )
