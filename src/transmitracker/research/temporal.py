"""Snapshot comparison only: no arrivals, measured trip durations or collector state."""

import math
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256

from transmitracker.catalog.common import BOGOTA
from transmitracker.catalog.queries import Catalog
from transmitracker.gtfs.realtime import decode_realtime, observations, timestamp_info

EARTH = 6371000


def capture_record(
    payload: bytes,
    *,
    received_at: datetime,
    source: str,
    origin: str,
    receipt_timestamp_verified: bool = True,
) -> dict:
    if origin not in {"real_network_capture", "saved_real_snapshot", "synthetic_fixture"}:
        raise ValueError("An explicit evidence origin is required")
    feed = decode_realtime(payload)
    if feed.header.incrementality != 0:
        raise ValueError("This diagnostic accepts complete snapshots only")
    timestamp = feed.header.timestamp if feed.header.HasField("timestamp") else None
    vehicles = observations(feed, now=received_at)
    messages = {entity.id: entity.vehicle for entity in feed.entity if entity.HasField("vehicle")}
    for record in vehicles:
        record["reported_fields"] = [f.name for f, _ in messages[record["entity_id"]].ListFields()]
    return {
        "origin": origin,
        "source": source,
        "received_at": received_at.isoformat(),
        "receipt_timestamp_verified": receipt_timestamp_verified,
        "payload_sha256": sha256(payload).hexdigest(),
        "feed": timestamp_info(timestamp, received_at),
        "vehicles": vehicles,
    }


def distance_m(a, b):
    lat1, lat2 = math.radians(a[0]), math.radians(b[0])
    delta_lat, delta_lon = lat2 - lat1, math.radians(b[1] - a[1])
    v = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH * math.asin(min(1, math.sqrt(v)))


def project(position, points):
    """Local equirectangular projection; flags competing distant shape branches.

    5 m residual ties / 100 m progress separation are diagnostic candidates,
    not calibrated route matching. No projection means no progress conclusion.
    """
    if len(points) < 2:
        return None
    reference_lat, reference_lon = points[0]

    def xy(point):
        return (
            EARTH * math.radians(point[1] - reference_lon) * math.cos(math.radians(reference_lat)),
            EARTH * math.radians(point[0] - reference_lat),
        )

    px, py = xy(position)
    candidates, progress = [], 0.0
    for first, last in zip(points, points[1:], strict=False):
        ax, ay = xy(first)
        bx, by = xy(last)
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy)
        fraction = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / length**2)) if length else 0
        residual = math.hypot(px - (ax + fraction * dx), py - (ay + fraction * dy))
        candidates.append((residual, progress + fraction * length))
        progress += length
    best = min(candidates)
    tied = [p for residual, p in candidates if residual <= best[0] + 5]
    return {
        "distance_to_shape_m": round(best[0], 3),
        "progress_m": round(best[1], 3),
        "ambiguous_projection": max(tied) - min(tied) > 100,
    }


class TemporalAnalyzer:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self._shapes = {}

    def shape(self, shape_id):
        if shape_id in self._shapes:
            return self._shapes[shape_id]
        if len(self._shapes) >= 128:
            self._shapes.pop(next(iter(self._shapes)))
        result = tuple(
            (r[0], r[1])
            for r in self.catalog.connection.execute(
                "SELECT latitude,longitude FROM shape_points WHERE shape_id=? ORDER BY sequence",
                (shape_id,),
            )
        )
        self._shapes[shape_id] = result
        return result

    def association(self, record):
        trip = self.catalog.connection.execute(
            "SELECT * FROM trips WHERE trip_id=?", (record["trip_id"],)
        ).fetchone()
        if not trip:
            return {"classification": "unresolved", "reason": "trip_id_not_in_catalog"}
        if trip["route_id"] != record["route_id"]:
            return {"classification": "contradictory", "reason": "trip_route_conflict"}
        if (
            record["direction_id"] is not None
            and trip["direction_id"] is not None
            and trip["direction_id"] != record["direction_id"]
        ):
            return {"classification": "contradictory", "reason": "direction_conflict"}
        if (
            record["current_stop_sequence"] is None
            or not record["stop_id"]
            or not record["start_date"]
        ):
            return {"classification": "ambiguous", "reason": "incomplete_descriptor"}
        try:
            day = datetime.strptime(record["start_date"], "%Y%m%d").date()
        except ValueError:
            return {"classification": "contradictory", "reason": "invalid_service_date"}
        if trip["service_id"] not in self.catalog.active_services(day):
            return {"classification": "contradictory", "reason": "inactive_service"}
        stop = self.catalog.connection.execute(
            "SELECT stop_id FROM stop_times WHERE trip_pk=? AND sequence=?",
            (trip["trip_pk"], record["current_stop_sequence"]),
        ).fetchone()
        if not stop or stop[0] != record["stop_id"]:
            return {"classification": "contradictory", "reason": "stop_sequence_conflict"}
        return {
            "classification": "verified",
            "reason": "exact_catalog_references_only",
            "scope": "route_trip_stop_sequence_and_service_not_operational_instance",
            "pattern_id": trip["pattern_id"],
            "shape_id": trip["shape_id"],
        }

    def analyze(self, captures: list[dict]) -> dict:
        if any(datetime.fromisoformat(c["received_at"]).tzinfo is None for c in captures):
            raise ValueError("Capture timestamps must have timezone")
        captures = sorted(captures, key=lambda c: c["received_at"])
        classes, changes, pairs, previous = Counter(), Counter(), [], {}
        origins = sorted({c["origin"] for c in captures})
        if "synthetic_fixture" in origins and len(origins) > 1:
            raise ValueError("Analyze real and synthetic evidence separately")
        cohorts, last_cohort = [], {}
        reasons, samples = Counter(), defaultdict(list)
        for capture_index, capture in enumerate(captures):
            grouped = defaultdict(list)
            for record in capture["vehicles"]:
                if record["vehicle_id"]:
                    grouped[record["vehicle_id"]].append(record)
                else:
                    classes["unresolved"] += 1
            current_ids = set(grouped)
            prior_cohort = last_cohort.get(capture["source"])
            if prior_cohort is not None:
                cohorts.append(
                    {
                        "source": capture["source"],
                        "from_capture": prior_cohort[0],
                        "to_capture": capture["received_at"],
                        "common_vehicle_ids": len(current_ids & prior_cohort[1]),
                        "appeared_vehicle_ids": sorted(current_ids - prior_cohort[1]),
                        "disappeared_vehicle_ids": sorted(prior_cohort[1] - current_ids),
                    }
                )
            last_cohort[capture["source"]] = (capture["received_at"], current_ids)
            for vehicle_id, rows in grouped.items():
                if len(rows) != 1:
                    classes["ambiguous"] += len(rows)
                    previous.pop((capture["source"], vehicle_id), None)
                    continue
                record = rows[0]
                association = self.association(record)
                if (
                    capture["feed"]["freshness"] != "recent"
                    or record["reported"]["freshness"] != "recent"
                ):
                    association = {
                        "classification": "unresolved",
                        "reason": "stale_missing_or_future_timestamp",
                    }
                classes[association["classification"]] += 1
                reasons[association["reason"]] += 1
                bucket = samples[association["classification"]]
                if len(bucket) < 3:
                    bucket.append(
                        {
                            "vehicle_id": vehicle_id,
                            "trip_id": record["trip_id"],
                            "route_id": record["route_id"],
                            "stop_id": record["stop_id"],
                            "current_stop_sequence": record["current_stop_sequence"],
                            "assessment": association,
                        }
                    )
                namespace = (capture["source"], vehicle_id)
                old = previous.get(namespace)
                if old and old[0] == capture_index - 1:
                    prior = old[1]
                    changed = {
                        key: prior[key] != record[key]
                        for key in (
                            "vehicle_id",
                            "trip_id",
                            "route_id",
                            "start_time",
                            "start_date",
                            "current_stop_sequence",
                        )
                    }
                    changes.update(key for key, value in changed.items() if value)
                    pair = {
                        "vehicle_id": vehicle_id,
                        "from_capture": old[2],
                        "to_capture": capture["received_at"],
                        "changed": changed,
                        "association": association,
                        "trajectory_status": "insufficient_evidence",
                    }
                    first_ts, last_ts = (
                        prior["reported"]["timestamp"],
                        record["reported"]["timestamp"],
                    )
                    delta = (
                        last_ts - first_ts if first_ts is not None and last_ts is not None else None
                    )
                    pair["gps_delta_seconds"] = delta
                    first_sequence, last_sequence = (
                        prior["current_stop_sequence"],
                        record["current_stop_sequence"],
                    )
                    pair["sequence_progress"] = (
                        None
                        if first_sequence is None or last_sequence is None
                        else "forward"
                        if last_sequence > first_sequence
                        else "reverse"
                        if last_sequence < first_sequence
                        else "unchanged"
                    )
                    pair["start_time_changed_with_new_gps"] = bool(
                        delta and delta > 0 and changed["start_time"]
                    )
                    pair["start_time_equals_gps_clock"] = bool(
                        last_ts is not None
                        and record["start_time"]
                        == datetime.fromtimestamp(last_ts, BOGOTA).strftime("%H:%M:%S")
                    )
                    if changed["start_time"] and association["classification"] == "verified":
                        pair["association"] = {
                            "classification": "ambiguous",
                            "reason": "start_time_changed_instance_not_verified",
                        }
                    if (
                        delta is not None
                        and delta > 0
                        and all(
                            r["latitude"] is not None and r["longitude"] is not None
                            for r in (prior, record)
                        )
                    ):
                        distance = distance_m(
                            (prior["latitude"], prior["longitude"]),
                            (record["latitude"], record["longitude"]),
                        )
                        pair.update(
                            displacement_m=round(distance, 3),
                            apparent_speed_mps=round(distance / delta, 3),
                        )
                        same_descriptor = not any(
                            changed[k] for k in ("trip_id", "route_id", "start_date")
                        )
                        if (
                            same_descriptor
                            and association["classification"] == "verified"
                            and old[3]["classification"] == "verified"
                            and delta <= 300
                        ):
                            points = self.shape(association["shape_id"])
                            first = project((prior["latitude"], prior["longitude"]), points)
                            last = project((record["latitude"], record["longitude"]), points)
                            pair.update(first_projection=first, last_projection=last)
                            if (
                                first
                                and last
                                and not first["ambiguous_projection"]
                                and not last["ambiguous_projection"]
                                and max(first["distance_to_shape_m"], last["distance_to_shape_m"])
                                <= 150
                            ):
                                movement = last["progress_m"] - first["progress_m"]
                                pair["progress_delta_m"] = round(movement, 3)
                                pair["geometric_progress"] = (
                                    "forward"
                                    if movement > 15
                                    else "reverse"
                                    if movement < -15
                                    else "indeterminate"
                                )
                                if changed["start_time"]:
                                    pair["trajectory_status"] = "ambiguous_instance_start_time"
                                elif pair["apparent_speed_mps"] > 40 or movement < -15:
                                    pair["trajectory_status"] = (
                                        "contradictory_progress_candidate_threshold"
                                    )
                                    pair["association"] = {
                                        "classification": "contradictory",
                                        "reason": "progress_or_displacement_inconsistent_under_diagnostic_thresholds",
                                    }
                                else:
                                    pair["trajectory_status"] = (
                                        "compatible_geometry_not_confirmed_run"
                                    )
                    elif delta == 0:
                        pair["trajectory_status"] = "unchanged_gps_timestamp_not_new_movement"
                    elif delta is not None and delta < 0:
                        pair["trajectory_status"] = "out_of_order"
                    pairs.append(pair)
                previous[namespace] = (capture_index, record, capture["received_at"], association)
        real = [
            c for c in captures if c["origin"] in {"real_network_capture", "saved_real_snapshot"}
        ]
        unique_real = {(c["payload_sha256"], c["received_at"]) for c in real}
        return {
            "evidence_origins": origins,
            "capture_count": len(captures),
            "unique_real_captures": len(unique_real),
            "real_temporal_validation": len(unique_real) >= 2
            and "synthetic_fixture" not in origins
            and all(c.get("receipt_timestamp_verified", False) for c in real)
            and any((p["gps_delta_seconds"] or 0) > 0 for p in pairs),
            "operational_identity_validated": False,
            "catalog_sha256": self.catalog.info()["sha256"],
            "reference_associations": dict(classes),
            "reference_reason_counts": dict(reasons),
            "reference_association_samples": dict(samples),
            "field_change_counts": dict(changes),
            "vehicle_cohort_transitions": cohorts,
            "temporal_associations": dict(
                Counter(p["association"]["classification"] for p in pairs)
            ),
            "compared_vehicle_pairs": len(pairs),
            "pairs": pairs,
            "arrivals_inferred": 0,
            "travel_durations_inferred": 0,
            "thresholds": {
                "freshness_seconds": 300,
                "max_projection_distance_m": 150,
                "ambiguous_branch_tie_m": 5,
                "progress_noise_m": 15,
                "apparent_speed_mps": 40,
            },
            "limitations": [
                "Verified means exact catalog references, not a proven operational trip instance.",
                "Geometric thresholds are diagnostic candidates, not calibrated tracking.",
                "No vehicle-ID suffix is used to infer routes.",
                "vehicle_id stability is measured as cohort overlap; a renumbered vehicle cannot be identified by assumption.",
            ],
        }
