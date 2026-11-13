"""Bounded crossing estimates; no extrapolation, confirmed boarding or GPS-derived ETA."""

from transmitracker.reconstruction.models import (
    Confidence,
    EventKind,
    Measurement,
    StopEvent,
    digest,
)


def crossing_events(segment, rows, projections, geometry, parameters):
    events = []
    trusted = segment.identity.confidence == Confidence.SYNTHETIC
    for stop in geometry.stops:
        common = (
            segment.identity.identity_id,
            segment.segment_id,
            geometry.route_id,
            geometry.pattern_id,
            stop.stop_id,
            stop.sequence,
        )
        support = None
        if stop.progress_m is not None:
            # Strictly before/after the GPS error band. A near-stop fix alone is not a crossing.
            before = None
            for index, projection in enumerate(projections):
                if projection.progress_m < stop.progress_m - parameters.gps_error_m:
                    before = index
                elif (
                    projection.progress_m > stop.progress_m + parameters.gps_error_m
                    and before is not None
                ):
                    support = (before, index)
                    break
        if support is None:
            reason = (
                stop.reason
                if stop.progress_m is None
                else "missing_before_or_after_crossing_evidence"
            )
            events.append(
                StopEvent(
                    digest((common, reason)),
                    *common,
                    EventKind.UNKNOWN,
                    None,
                    None,
                    None,
                    (),
                    "none",
                    None,
                    Confidence.REJECTED,
                    False,
                    (reason,),
                )
            )
            continue
        first, last = support
        a, b = projections[first], projections[last]
        t0, t1 = rows[first][0].reported_at, rows[last][0].reported_at
        seconds, metres = t1 - t0, b.progress_m - a.progress_m
        observed_speed = metres / seconds
        # Observed velocities around the bracket; never a default/scheduled/visual speed.
        speeds = segment.speeds_mps[max(0, first - 1) : min(len(segment.speeds_mps), last + 1)]
        stable = (
            bool(speeds)
            and observed_speed > 0
            and max(speeds) - min(speeds) <= parameters.speed_variation_ratio * observed_speed
        )
        estimate = None
        method = "observed_monotone_bracket_interval_only"
        if seconds <= parameters.interpolation_gap_s and stable:
            estimate = t0 + (stop.progress_m - a.progress_m) / metres * seconds
            method = "conditional_linear_interpolation_between_observed_fixes"
        ids = tuple(row[1].normalized_id for row in rows[first : last + 1])
        low, high = t0 - parameters.timestamp_error_s, t1 + parameters.timestamp_error_s
        reasons = (
            ("synthetic_identity_and_continuity",)
            if trusted
            else ("operational_identity_not_verified",)
        )
        events.append(
            StopEvent(
                digest((common, ids, method)),
                *common,
                EventKind.CROSSING,
                low,
                high,
                estimate,
                ids,
                method,
                high - low,
                segment.identity.confidence,
                trusted,
                reasons,
            )
        )
    # Published STOPPED_AT plus repeated actual fixes supports stationarity, never observed arrival/doors.
    for stop in geometry.stops:
        if stop.progress_m is None:
            continue
        dwell = []
        for row, projection in zip(rows, projections, strict=True):
            original, normalized = row
            at_stop = (
                original.current_status == "STOPPED_AT"
                and original.stop_id == stop.stop_id
                and original.current_stop_sequence == stop.sequence
                and abs(projection.progress_m - stop.progress_m) <= parameters.stop_radius_m
            )
            if at_stop:
                dwell.append(row)
            else:
                dwell = []
            if (
                len(dwell) >= 3
                and dwell[-1][0].reported_at - dwell[0][0].reported_at >= parameters.min_dwell_s
            ):
                longitudes = [r[0].longitude for r in dwell]
                latitudes = [r[0].latitude for r in dwell]
                # Projection span is independently checked for observed stationarity.
                from transmitracker.research.temporal import distance_m

                if (
                    distance_m((min(latitudes), min(longitudes)), (max(latitudes), max(longitudes)))
                    > parameters.gps_error_m
                ):
                    continue
                ids = tuple(r[1].normalized_id for r in dwell)
                common = (
                    segment.identity.identity_id,
                    segment.segment_id,
                    geometry.route_id,
                    geometry.pattern_id,
                    stop.stop_id,
                    stop.sequence,
                )
                low, high = dwell[0][0].reported_at, dwell[-1][0].reported_at
                events.append(
                    StopEvent(
                        digest((common, ids, "stationary")),
                        *common,
                        EventKind.STOP,
                        low,
                        high,
                        None,
                        ids,
                        "repeated_stationary_gps_and_explicit_published_stop_status_not_arrival",
                        high - low,
                        segment.identity.confidence,
                        trusted,
                        ("stationarity_not_arrival_or_boarding",),
                    )
                )
                break
    return events


def measure(segment, events, leg, parameters):
    common = (
        segment.identity.identity_id,
        segment.segment_id,
        leg.pattern_id,
        leg.origin_stop_id,
        leg.origin_sequence,
        leg.destination_stop_id,
        leg.destination_sequence,
    )
    reasons = []
    if leg.destination_sequence <= leg.origin_sequence or segment.pattern_id != leg.pattern_id:
        reasons.append("incompatible_or_non_downstream_occurrences")
    origin = next(
        (
            e
            for e in events
            if e.segment_id == segment.segment_id
            and e.kind == EventKind.CROSSING
            and e.stop_id == leg.origin_stop_id
            and e.sequence == leg.origin_sequence
        ),
        None,
    )
    destination = next(
        (
            e
            for e in events
            if e.segment_id == segment.segment_id
            and e.kind == EventKind.CROSSING
            and e.stop_id == leg.destination_stop_id
            and e.sequence == leg.destination_sequence
        ),
        None,
    )
    if not origin or not destination:
        reasons.append("insufficient_endpoint_events_in_same_segment")
    low = high = estimate = None
    ids = tuple(e.event_id for e in (origin, destination) if e is not None)
    if origin and destination:
        low = max(0.0, destination.earliest_at - origin.latest_at)
        high = destination.latest_at - origin.earliest_at
        if high < 0:
            reasons.append("temporal_event_order_conflict")
        elif high - low > parameters.max_duration_uncertainty_s:
            reasons.append("duration_uncertainty_too_wide")
        if not origin.accepted or not destination.accepted:
            reasons.append("operational_identity_not_verified")
        if origin.estimated_at is not None and destination.estimated_at is not None:
            estimate = destination.estimated_at - origin.estimated_at
    return Measurement(
        digest((common, ids)),
        *common,
        ids,
        low,
        high,
        estimate,
        None,
        None,
        not reasons,
        segment.identity.confidence if not reasons else Confidence.REJECTED,
        tuple(reasons) or ("bounded_in_vehicle_time_estimate_only",),
    )
