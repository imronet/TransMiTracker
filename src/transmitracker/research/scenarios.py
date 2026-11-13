"""Build an explicitly synthetic sequence for local replay; never fetches feeds."""

from datetime import datetime, timedelta

from google.transit import gtfs_realtime_pb2 as pb


def synthetic_snapshots(scenario: dict):
    if scenario.get("origin") != "synthetic_scenario_not_real_api_captures":
        raise ValueError("Expected explicitly synthetic provenance")
    reference = datetime.fromisoformat(scenario["reference_time"])
    if reference.tzinfo is None:
        raise ValueError("Reference must be timezone-aware")
    for spec in scenario["snapshots"]:
        captured = reference + timedelta(seconds=spec["offset_seconds"])
        feed = pb.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.incrementality = pb.FeedHeader.FULL_DATASET
        feed.header.timestamp = int(captured.timestamp())
        for number, record in enumerate(spec["vehicles"]):
            entity = feed.entity.add()
            entity.id = f"SYN_ENTITY_{number}"
            vehicle = entity.vehicle
            for key in ("trip_id", "route_id", "start_date", "start_time", "direction_id"):
                if key in record:
                    setattr(vehicle.trip, key, record[key])
            if "vehicle_id" in record:
                vehicle.vehicle.id = record["vehicle_id"]
            vehicle.position.latitude = record["latitude"]
            vehicle.position.longitude = record["longitude"]
            vehicle.timestamp = int(captured.timestamp()) - record.get("age_seconds", 0)
            if "stop_id" in record:
                vehicle.stop_id = record["stop_id"]
            if "sequence" in record:
                vehicle.current_stop_sequence = record["sequence"]
        yield captured, feed.SerializeToString(deterministic=True)
