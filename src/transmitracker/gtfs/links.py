"""Report exact ID joins, without guessing trips from route names or GPS."""

from collections import Counter
from datetime import datetime

from transmitracker.gtfs.realtime import observations
from transmitracker.gtfs.static import StaticFeed


def analyze_links(static: StaticFeed, realtime, *, now: datetime) -> dict:
    counts = Counter()
    examples = []
    example_statuses = set()
    records = observations(realtime, now=now)
    for record in records:
        trip = static.trips.get(record["trip_id"])
        route_id = record["route_id"]
        counts["vehicles"] += 1
        counts["trip_id_present"] += record["trip_id"] is not None
        counts["trip_id_matched"] += trip is not None
        counts["route_id_present"] += route_id is not None
        counts["route_id_matched"] += route_id in static.routes
        counts["stop_id_present"] += record["stop_id"] is not None
        counts["stop_id_matched"] += record["stop_id"] in static.stops
        conflict = bool(trip and route_id is not None and route_id != trip["route_id"])
        counts["trip_route_conflicts"] += conflict
        direction_conflict = bool(
            trip
            and record["direction_id"] is not None
            and trip.get("direction_id", "") != ""
            and str(record["direction_id"]) != trip["direction_id"]
        )
        counts["direction_conflicts"] += direction_conflict
        resolved_route = trip["route_id"] if trip and not conflict else route_id
        route = static.routes.get(resolved_route)
        status = (
            "conflict"
            if conflict or direction_conflict
            else "trip_match"
            if trip
            else "route_only"
            if route
            else "unmapped"
        )
        counts[f"status_{status}"] += 1
        if status not in example_statuses:
            example_statuses.add(status)
            examples.append(
                {
                    **record,
                    "join_status": status,
                    "static_trip_route_id": trip["route_id"] if trip else None,
                    "shape_id": trip.get("shape_id") if trip else None,
                    "service_id": trip.get("service_id") if trip else None,
                    "route_short_name": route.get("route_short_name") if route else None,
                    "route_long_name": route.get("route_long_name") if route else None,
                    "stop_known": record["stop_id"] in static.stops,
                    "trip_instance_resolved": False,
                }
            )
    update_counts = Counter()
    for entity in realtime.entity:
        if entity.is_deleted or not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        trip = static.trips.get(update.trip.trip_id)
        update_counts["trip_updates"] += 1
        update_counts["trip_id_matched"] += trip is not None
        update_counts["route_id_present"] += update.trip.HasField("route_id")
        update_counts["route_id_matched"] += update.trip.route_id in static.routes
        update_counts["trip_route_conflicts"] += bool(
            trip and update.trip.HasField("route_id") and update.trip.route_id != trip["route_id"]
        )
        for stop in update.stop_time_update:
            update_counts["stop_updates"] += 1
            update_counts["stop_id_present"] += stop.HasField("stop_id")
            update_counts["stop_id_matched"] += (
                stop.HasField("stop_id") and stop.stop_id in static.stops
            )
    return {
        "join_type": "exact_ids_within_official_provider",
        "vehicle_counts": dict(counts),
        "trip_update_counts": dict(update_counts),
        "examples": examples,
        "limitations": [
            "An exact trip_id join does not validate service date or identify a frequency-based trip instance.",
            "No normalization or cross-provider mapping is assumed.",
            "Vehicle IDs and entity IDs are distinct; no static vehicle table is assumed.",
        ],
    }
