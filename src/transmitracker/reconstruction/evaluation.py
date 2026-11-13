"""Synthetic truth only: point errors, interval coverage, false positives and safety."""

import math
from collections import Counter
from statistics import median

from transmitracker.reconstruction.geometry import GeometryCatalog
from transmitracker.reconstruction.models import EventKind, Parameters
from transmitracker.research.temporal import distance_m


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def baseline_predictions(case, catalog, radius_m=80):
    """Simple first observed fix inside a geofence; no interpolation or animation.

    Deliberately no topology/continuity gate. Outputs are evaluation-only candidates,
    never written as accepted analytical events or historical measurements.
    """
    geometries = GeometryCatalog(catalog, Parameters())
    vehicles = {}
    for snapshot in case.snapshots:
        for row in snapshot.observations:
            vehicles.setdefault((row.source, row.vehicle_id), []).append(row)
    predictions = []
    for (_, vehicle_id), rows in vehicles.items():
        rows = sorted(rows, key=lambda row: row.reported_at or 0)
        geometry = geometries.load(rows[0].trip_id)
        if not geometry:
            continue
        for stop in geometry.stops[:3]:
            match = next(
                (
                    r
                    for r in rows
                    if r.latitude is not None
                    and r.longitude is not None
                    and -90 <= r.latitude <= 90
                    and -180 <= r.longitude <= 180
                    and distance_m((r.latitude, r.longitude), (stop.latitude, stop.longitude))
                    <= radius_m
                ),
                None,
            )
            if match:
                predictions.append(
                    {
                        "vehicle_id": vehicle_id,
                        "pattern_id": geometry.pattern_id,
                        "stop_id": stop.stop_id,
                        "sequence": stop.sequence,
                        "at": match.reported_at,
                        "low": match.reported_at,
                        "high": match.reported_at,
                    }
                )
    return predictions


def metrics(predictions, truth, vehicle_count, rejected_vehicles):
    truth_map = {
        (e["vehicle_id"], e["pattern_id"], e["stop_id"], e["sequence"]): e["at"] for e in truth
    }
    used, errors, midpoints, covered = set(), [], [], []
    false_positive = 0
    for prediction in predictions:
        key = tuple(prediction[k] for k in ("vehicle_id", "pattern_id", "stop_id", "sequence"))
        actual = truth_map.get(key)
        low, high, point = prediction["low"], prediction["high"], prediction["at"]
        matched = (
            actual is not None
            and key not in used
            and (abs(point - actual) <= 30 if point is not None else low <= actual <= high)
        )
        if not matched:
            false_positive += 1
            continue
        used.add(key)
        covered.append(low <= actual <= high)
        if point is not None:
            errors.append(abs(point - actual))
        else:
            # Evaluation proxy only; no midpoint is inserted into StopEvent.estimated_at.
            midpoints.append(abs((low + high) / 2 - actual))
    return {
        "truth_events": len(truth_map),
        "detected_events": len(used),
        "detected_percent": 100 * len(used) / len(truth_map) if truth_map else None,
        "false_positives": false_positive,
        "point_estimate_count": len(errors),
        "median_absolute_error_s": median(errors) if errors else None,
        "p90_absolute_error_s": percentile(errors, 0.9),
        "interval_midpoint_proxy_median_error_s": median(midpoints) if midpoints else None,
        "interval_midpoint_proxy_p90_error_s": percentile(midpoints, 0.9),
        "uncertainty_interval_coverage_percent": 100 * sum(covered) / len(covered)
        if covered
        else None,
        "rejected_trajectory_percent": 100 * rejected_vehicles / vehicle_count
        if vehicle_count
        else None,
        "event_matching_tolerance_s": 30,
        "interval_only_is_not_exact_time": True,
    }


def evaluate_case(case, result, catalog):
    segments = {s.segment_id: s for s in result.segments}
    accepted = [
        e for e in result.events if e.accepted and e.kind == EventKind.CROSSING and e.sequence <= 30
    ]
    predicted = [
        {
            "vehicle_id": segments[e.segment_id].identity.published_descriptor[2],
            "pattern_id": e.pattern_id,
            "stop_id": e.stop_id,
            "sequence": e.sequence,
            "at": e.estimated_at,
            "low": e.earliest_at,
            "high": e.latest_at,
        }
        for e in accepted
    ]
    vehicles = {o.vehicle_id for s in case.snapshots for o in s.observations if o.vehicle_id}
    measured = {
        segments[m.segment_id].identity.published_descriptor[2]
        for m in result.measurements
        if m.accepted
    }
    baseline = baseline_predictions(case, catalog)
    baseline_measured = {
        v
        for v in vehicles
        if any(p["vehicle_id"] == v and p["sequence"] == 10 for p in baseline)
        and any(p["vehicle_id"] == v and p["sequence"] == 30 for p in baseline)
    }
    return {
        "scenario": case.name,
        "origin": "synthetic_truth_not_real_validation",
        "baseline_radius_m": 80,
        "scored_occurrences": "first_three_published_stop_occurrences_only",
        "proposed": metrics(predicted, case.truth_events, len(vehicles), len(vehicles - measured)),
        "baseline": metrics(
            baseline, case.truth_events, len(vehicles), len(vehicles - baseline_measured)
        ),
        "accepted_measurements": sum(m.accepted for m in result.measurements),
        "measurement_rejection_reasons": dict(
            Counter(reason for m in result.measurements if not m.accepted for reason in m.reasons)
        ),
        "measurement_safety_required_rejection": case.must_reject_measurement,
        "unsafe_accepted_measurements": len(measured) if case.must_reject_measurement else 0,
        "baseline_unsafe_candidate_measurements": len(baseline_measured)
        if case.must_reject_measurement
        else 0,
        "rejection_reasons": dict(Counter(r.reason for r in result.rejections)),
        "interval_only_crossings": sum(e.estimated_at is None for e in accepted),
        "observed_stationarity_events": sum(
            e.kind == EventKind.STOP and e.accepted for e in result.events
        ),
        "observed_arrivals": sum(e.kind == EventKind.ARRIVAL for e in result.events),
    }
