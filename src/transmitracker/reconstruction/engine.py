"""Deterministic batch-only GPS reconstruction with conservative identity gates."""

import math
from collections import defaultdict
from dataclasses import replace

from transmitracker.catalog.common import gtfs_seconds
from transmitracker.reconstruction import ALGORITHM_VERSION, implementation_hash
from transmitracker.reconstruction.events import crossing_events, measure
from transmitracker.reconstruction.geometry import GeometryCatalog, select_projection
from transmitracker.reconstruction.models import (
    CandidateIdentity,
    Confidence,
    NormalizedObservation,
    Parameters,
    Projection,
    ReconstructionResult,
    Rejection,
    TrajectorySegment,
    digest,
)
from transmitracker.research.temporal import TemporalAnalyzer, distance_m


def namespace(original):
    return original.source, original.endpoint, original.vehicle_id


def descriptor(original):
    return (
        *namespace(original),
        original.trip_id,
        original.route_id,
        original.start_date,
        original.start_time,
        original.direction_id,
    )


class ReconstructionEngine:
    def __init__(self, catalog, parameters=None):
        self.catalog, self.parameters = catalog, parameters or Parameters()
        self.catalog_sha256 = catalog.info()["sha256"]
        self.algorithm_sha256 = implementation_hash()
        self.geometry = GeometryCatalog(catalog, self.parameters)
        self.associations = TemporalAnalyzer(catalog)

    def normalize(self, snapshots):
        p = self.parameters
        rows, normalized, rejections, warnings = [], {}, [], []
        latest = {}
        resets, feed_resets = set(), set()
        seen_reports, seen_feeds = {}, {}
        for frame in sorted(
            (s for s in snapshots if s.received_at is not None and math.isfinite(s.received_at)),
            key=lambda s: s.received_at,
        ):
            provider = frame.source, frame.endpoint
            previous_feed = seen_feeds.get(provider)
            if frame.feed_as_of is not None and math.isfinite(frame.feed_as_of):
                if previous_feed is not None and frame.feed_as_of < previous_feed:
                    feed_resets.add(frame.snapshot_id)
                seen_feeds[provider] = frame.feed_as_of
            for original in frame.observations:
                key, ts = namespace(original), original.reported_at
                if ts is not None and math.isfinite(ts):
                    if key in seen_reports and seen_reports[key] - ts > p.clock_reset_s:
                        resets.add((frame.snapshot_id, original.observation_id))
                    seen_reports[key] = max(seen_reports.get(key, ts), ts)
        processed_snapshots = set()
        for snapshot in snapshots:
            if snapshot.snapshot_id in processed_snapshots:
                warnings.append("duplicate_snapshot_input")
                continue
            processed_snapshots.add(snapshot.snapshot_id)
            for index, original in enumerate(snapshot.observations):
                reasons = []
                if original.position_kind != "observed":
                    reasons.append("visual_or_extrapolated_position_is_not_gps_evidence")
                if snapshot.snapshot_id in feed_resets:
                    reasons.append("feed_timestamp_regressed_under_verified_receipt_order")
                if (snapshot.snapshot_id, original.observation_id) in resets:
                    reasons.append("possible_vehicle_clock_reset_or_delayed_report")
                ts, lat, lon = original.reported_at, original.latitude, original.longitude
                if ts is None or not math.isfinite(ts) or ts <= 0:
                    reasons.append("missing_or_invalid_vehicle_timestamp")
                if (
                    lat is None
                    or lon is None
                    or not math.isfinite(lat)
                    or not math.isfinite(lon)
                    or not -90 <= lat <= 90
                    or not -180 <= lon <= 180
                ):
                    reasons.append("invalid_or_missing_coordinates")
                reference = (
                    snapshot.received_at
                    if snapshot.received_at is not None
                    else snapshot.feed_as_of
                )
                if reference is None or not math.isfinite(reference):
                    reasons.append("missing_freshness_reference")
                elif ts is not None and math.isfinite(ts):
                    if reference - ts > p.max_age_s:
                        reasons.append("stale_vehicle_timestamp")
                    if ts - reference > p.future_tolerance_s:
                        reasons.append("future_vehicle_timestamp")
                if snapshot.feed_as_of is not None:
                    if not math.isfinite(snapshot.feed_as_of):
                        reasons.append("invalid_feed_timestamp")
                    if (
                        snapshot.received_at is not None
                        and snapshot.feed_as_of - snapshot.received_at > p.future_tolerance_s
                    ):
                        reasons.append("future_feed_timestamp")
                    if (
                        snapshot.received_at is not None
                        and snapshot.received_at - snapshot.feed_as_of > p.max_age_s
                    ):
                        reasons.append("stale_feed_timestamp")
                    if (
                        ts is not None
                        and math.isfinite(ts)
                        and ts - snapshot.feed_as_of > p.future_tolerance_s
                    ):
                        reasons.append("vehicle_ahead_of_feed")
                if not original.vehicle_id:
                    reasons.append("missing_vehicle_id_no_entity_fallback")
                if original.current_stop_sequence is not None and (
                    type(original.current_stop_sequence) is not int
                    or original.current_stop_sequence < 0
                ):
                    reasons.append("invalid_stop_sequence")
                try:
                    if gtfs_seconds(original.start_time or "") is None:
                        reasons.append("missing_start_time")
                except ValueError:
                    reasons.append("invalid_start_time")
                key = namespace(original)
                prior = latest.get(key)
                if ts is not None and math.isfinite(ts):
                    if prior is not None and ts < prior:
                        warnings.append("input_report_out_of_order")
                    latest[key] = max(prior or ts, ts)
                row = NormalizedObservation(
                    digest((snapshot.snapshot_id, index, original.observation_id)),
                    original.observation_id,
                    snapshot.snapshot_id,
                    original.source,
                    original.vehicle_id,
                    ts,
                    lat,
                    lon,
                    not reasons,
                    tuple(reasons),
                )
                rows.append((snapshot, original, row))
                normalized[row.normalized_id] = row
        # Preserve all sightings; neither a duplicate nor conflicting report creates movement.
        at_time = defaultdict(list)
        for snapshot, original, row in rows:
            if row.accepted:
                at_time[(namespace(original), original.reported_at)].append(
                    (snapshot, original, row)
                )
        for values in at_time.values():
            conflict = (
                len(
                    {
                        digest(
                            (
                                descriptor(v[1]),
                                v[1].latitude,
                                v[1].longitude,
                                v[1].stop_id,
                                v[1].current_stop_sequence,
                                v[1].current_status,
                            )
                        )
                        for v in values
                    }
                )
                > 1
            )
            for ordinal, (_, _original, row) in enumerate(values):
                if conflict or ordinal:
                    reason = (
                        "conflicting_reports_same_vehicle_timestamp"
                        if conflict
                        else "duplicate_observation"
                    )
                    normalized[row.normalized_id] = replace(row, accepted=False, reasons=(reason,))
        for row in normalized.values():
            rejections.extend(
                Rejection(row.normalized_id, "normalization", reason, (row.observation_id,))
                for reason in row.reasons
            )
        return rows, normalized, rejections, warnings

    def run(self, snapshots, *, legs=(), evidence=()):
        legs = tuple(dict.fromkeys(legs))
        snapshots, evidence = tuple(snapshots), tuple(evidence)
        origins = {s.origin for s in snapshots}
        if origins - {"synthetic_fixture", "saved_real_snapshot"}:
            raise ValueError("Unknown offline evidence origin")
        if any(
            o.source != s.source or o.endpoint != s.endpoint
            for s in snapshots
            for o in s.observations
        ):
            raise ValueError("Observation provenance differs from its snapshot")
        if len(origins) > 1:
            raise ValueError("Process real and synthetic snapshots in separate batches")
        if any(s.catalog_sha256 != self.catalog_sha256 for s in snapshots):
            raise ValueError("Snapshot catalog hash differs")
        if evidence and origins != {"synthetic_fixture"}:
            raise ValueError(
                "Synthetic identity evidence cannot authorize real operational identities"
            )
        for claim in evidence:
            if (
                claim.kind != "synthetic_identity_declaration"
                or not claim.evidence_reference
                or not claim.valid_from <= claim.valid_until
            ):
                raise ValueError("Invalid synthetic identity evidence")
        for leg in legs:
            self.catalog.validate_leg_structure(leg)
        rows, normalized, rejections, warnings = self.normalize(snapshots)
        grouped = defaultdict(list)
        presence = defaultdict(list)
        ordered_frames = sorted(
            snapshots,
            key=lambda s: (
                (s.received_at if s.received_at is not None else s.feed_as_of) or 0,
                s.snapshot_id,
            ),
        )
        ranks = {s.snapshot_id: index for index, s in enumerate(ordered_frames)}
        for snapshot in ordered_frames:
            presence[(snapshot.source, snapshot.endpoint)].append(
                (
                    ranks[snapshot.snapshot_id],
                    snapshot.complete,
                    {o.vehicle_id for o in snapshot.observations},
                )
            )
        for snapshot, original, row in rows:
            if original.vehicle_id:
                grouped[namespace(original)].append(
                    (snapshot, original, normalized[row.normalized_id])
                )
        segments, all_projections, events, measurements = [], [], [], []
        for values in grouped.values():
            values.sort(
                key=lambda v: (
                    v[1].reported_at
                    if v[1].reported_at is not None and math.isfinite(v[1].reported_at)
                    else -1,
                    v[2].normalized_id,
                )
            )
            current, projections, distances, speeds, motion = [], [], [], [], []

            def flush(
                reason,
                current=current,
                projections=projections,
                distances=distances,
                speeds=speeds,
                motion=motion,
            ):
                if not current:
                    return
                first = current[0][1]
                active_geometry = self.geometry.load(first.trip_id)
                published = descriptor(first)
                matches = [
                    claim
                    for claim in evidence
                    if (
                        claim.source,
                        claim.vehicle_id,
                        claim.trip_id,
                        claim.route_id,
                        claim.start_date,
                        claim.start_time,
                        claim.pattern_id,
                    )
                    == (
                        first.source,
                        first.vehicle_id,
                        first.trip_id,
                        first.route_id,
                        first.start_date,
                        first.start_time,
                        active_geometry.pattern_id,
                    )
                    and claim.valid_from <= current[0][1].reported_at
                    and claim.valid_until >= current[-1][1].reported_at
                ]
                trusted = len(matches) == 1 and len(current) >= 2
                identity = CandidateIdentity(
                    digest((self.catalog_sha256, published, active_geometry.pattern_id)),
                    published,
                    active_geometry.pattern_id,
                    True,
                    len(current) >= 2,
                    False,
                    Confidence.SYNTHETIC if trusted else Confidence.CANDIDATE,
                    tuple(digest(c) for c in matches),
                    ("synthetic_identity_declaration_only",)
                    if trusted
                    else ("operational_identity_not_verified",),
                )
                ids = tuple(row[2].normalized_id for row in current)
                segment = TrajectorySegment(
                    digest((identity.identity_id, ids)),
                    identity,
                    ids,
                    active_geometry.pattern_id,
                    current[0][1].reported_at,
                    current[-1][1].reported_at,
                    tuple(distances),
                    tuple(speeds),
                    tuple(motion),
                    reason,
                )
                segments.append(segment)
                calculated = crossing_events(
                    segment,
                    [(row[1], row[2]) for row in current],
                    projections,
                    active_geometry,
                    self.parameters,
                )
                events.extend(calculated)
                for leg in legs:
                    if leg.pattern_id == segment.pattern_id:
                        measurements.append(measure(segment, calculated, leg, self.parameters))
                all_projections.extend(projections)
                current.clear()
                projections.clear()
                distances.clear()
                speeds.clear()
                motion.clear()

            for snapshot, original, row in values:
                if not row.accepted:
                    if "duplicate_observation" not in row.reasons:
                        flush(row.reasons[0])
                    continue
                if current:
                    prior = current[-1][1]
                    delta = original.reported_at - prior.reported_at
                    reason = None
                    if descriptor(original) != descriptor(prior):
                        reason = (
                            "start_time_changed_restart_or_instability"
                            if (original.trip_id, original.route_id, original.start_date)
                            == (prior.trip_id, prior.route_id, prior.start_date)
                            and original.start_time != prior.start_time
                            else "published_descriptor_changed"
                        )
                    elif delta > self.parameters.max_gap_s:
                        reason = "observation_gap"
                    elif any(
                        complete and prior.vehicle_id not in ids
                        for rank, complete, ids in presence[(snapshot.source, snapshot.endpoint)]
                        if ranks[current[-1][0].snapshot_id] < rank < ranks[snapshot.snapshot_id]
                    ):
                        reason = "disappeared_between_complete_snapshots"
                    elif (
                        original.current_stop_sequence is not None
                        and prior.current_stop_sequence is not None
                        and original.current_stop_sequence < prior.current_stop_sequence
                    ):
                        reason = "reported_stop_sequence_regressed"
                    if reason:
                        rejections.append(
                            Rejection(
                                row.normalized_id,
                                "continuity",
                                reason,
                                (current[-1][2].normalized_id, row.normalized_id),
                            )
                        )
                        flush(reason)
                try:
                    association = self.associations.association(
                        {
                            "trip_id": original.trip_id,
                            "route_id": original.route_id,
                            "direction_id": original.direction_id,
                            "start_date": original.start_date,
                            "stop_id": original.stop_id,
                            "current_stop_sequence": original.current_stop_sequence,
                        }
                    )
                except (ValueError, TypeError):
                    association = {
                        "classification": "contradictory",
                        "reason": "invalid_descriptor",
                    }
                if association["classification"] != "verified":
                    reason = association["reason"]
                    rejections.append(
                        Rejection(
                            row.normalized_id,
                            "catalog_association",
                            reason,
                            (original.observation_id,),
                        )
                    )
                    flush(reason)
                    continue
                geometry = self.geometry.load(original.trip_id)
                if geometry is None:
                    rejections.append(Rejection(row.normalized_id, "geometry", "missing_shape"))
                    flush("missing_shape")
                    continue
                if current:
                    delta = original.reported_at - current[-1][1].reported_at
                    distance = distance_m(
                        (original.latitude, original.longitude),
                        (current[-1][1].latitude, current[-1][1].longitude),
                    )
                    if delta <= 0 or distance / delta > self.parameters.max_speed_mps:
                        rejections.append(
                            Rejection(row.normalized_id, "continuity", "implausible_observed_speed")
                        )
                        flush("implausible_observed_speed")
                        continue
                else:
                    delta, distance = None, None
                projected, support = select_projection(
                    geometry, original, self.parameters, projections[-1] if current else None, delta
                )
                if projected is None:
                    rejections.append(Rejection(row.normalized_id, "geometry", support))
                    flush(support)
                    continue
                projection = Projection(
                    row.normalized_id,
                    geometry.pattern_id,
                    geometry.shape_id,
                    projected.progress_m,
                    projected.residual_m,
                    projected.edge_index,
                    support,
                )
                if current:
                    along = projection.progress_m - projections[-1].progress_m
                    distances.append(distance)
                    speeds.append(max(distance, abs(along)) / delta)
                    motion.append(
                        "stationary"
                        if distance <= self.parameters.gps_error_m
                        and abs(along) <= self.parameters.gps_error_m
                        else "minor_backtrack_noise"
                        if along < 0
                        else "forward"
                    )
                current.append((snapshot, original, row))
                projections.append(projection)
            flush("end_of_offline_batch_not_arrival")
        # Missing vehicle IDs cannot silently disappear from the incident ledger.
        return ReconstructionResult(
            ALGORITHM_VERSION,
            self.catalog_sha256,
            self.parameters,
            snapshots,
            tuple(normalized.values()),
            tuple(segments),
            tuple(all_projections),
            tuple(events),
            tuple(measurements),
            tuple(rejections),
            evidence,
            tuple(warnings),
            tuple(legs),
            algorithm_sha256=self.algorithm_sha256,
        )
