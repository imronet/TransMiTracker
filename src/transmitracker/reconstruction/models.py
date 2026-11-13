"""Typed evidence, geometry, decisions and intervals; no visual positions."""

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum

from transmitracker.profiles.contracts import primitive


def canonical(value):
    def clean(item):
        if isinstance(item, float) and not math.isfinite(item):
            return {"$nonfinite": str(item)}
        if isinstance(item, dict):
            return {k: clean(v) for k, v in item.items()}
        if isinstance(item, list):
            return [clean(v) for v in item]
        return item

    return json.dumps(
        clean(primitive(value)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class Confidence(str, Enum):
    REJECTED = "rejected"
    CANDIDATE = "catalog_and_continuity_candidate_not_operationally_verified"
    SYNTHETIC = "synthetic_identity_validated_not_real_operation"


class EventKind(str, Enum):
    CROSSING = "estimated_crossing"
    ARRIVAL = "observed_arrival"  # Reserved for independent actual-arrival evidence; GPS cannot create it.
    STOP = "observed_stationarity_with_published_stop_status"
    UNKNOWN = "not_determinable"


@dataclass(frozen=True)
class Parameters:
    max_age_s: float = 300
    future_tolerance_s: float = 5
    max_gap_s: float = 120
    max_speed_mps: float = 35
    max_offset_m: float = 60
    projection_tie_m: float = 5
    branch_separation_m: float = 30
    backtrack_tolerance_m: float = 10
    gps_error_m: float = 8
    timestamp_error_s: float = 1
    interpolation_gap_s: float = 40
    speed_variation_ratio: float = 0.2
    min_dwell_s: float = 20
    stop_radius_m: float = 15
    max_duration_uncertainty_s: float = 85
    clock_reset_s: float = 120

    def __post_init__(self):
        if any(
            type(v) not in (int, float) or not math.isfinite(v) or v <= 0
            for v in self.__dict__.values()
        ):
            raise ValueError("Parameters must be finite positive numbers")


@dataclass(frozen=True)
class OriginalObservation:
    observation_id: str
    source: str
    endpoint: str | None
    entity_id: str | None
    vehicle_id: str | None
    trip_id: str | None
    route_id: str | None
    start_date: str | None
    start_time: str | None
    direction_id: int | None
    reported_at: float | None
    latitude: float | None
    longitude: float | None
    stop_id: str | None
    current_stop_sequence: int | None
    current_status: str | None
    raw_json: str
    position_kind: str = "observed"


@dataclass(frozen=True)
class ProviderSnapshot:
    snapshot_id: str
    source: str
    endpoint: str | None
    catalog_sha256: str
    origin: str
    payload_sha256: str
    feed_as_of: float | None
    received_at: float | None
    receipt_reference_at: float | None
    complete: bool
    observations: tuple[OriginalObservation, ...]
    provenance_json: str


@dataclass(frozen=True)
class NormalizedObservation:
    normalized_id: str
    observation_id: str
    snapshot_id: str
    source: str
    vehicle_id: str | None
    reported_at: float | None
    latitude: float | None
    longitude: float | None
    accepted: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class IdentityEvidence:
    """Synthetic generator's identity declaration, never accepted for real snapshots."""

    source: str
    vehicle_id: str
    trip_id: str
    route_id: str
    start_date: str
    start_time: str
    pattern_id: str
    valid_from: float
    valid_until: float
    evidence_reference: str
    kind: str = "synthetic_identity_declaration"


@dataclass(frozen=True)
class CandidateIdentity:
    identity_id: str
    published_descriptor: tuple
    pattern_id: str
    catalog_references_verified: bool
    continuity_supported: bool
    operationally_verified: bool
    confidence: Confidence
    evidence_ids: tuple[str, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Projection:
    normalized_id: str
    pattern_id: str
    shape_id: str
    progress_m: float
    residual_m: float
    edge_index: int
    support: str


@dataclass(frozen=True)
class TrajectorySegment:
    segment_id: str
    identity: CandidateIdentity
    normalized_ids: tuple[str, ...]
    pattern_id: str
    started_at: float
    ended_at: float
    distances_m: tuple[float, ...]
    speeds_mps: tuple[float, ...]
    motion: tuple[str, ...]
    termination_reason: str


@dataclass(frozen=True)
class StopEvent:
    event_id: str
    identity_id: str
    segment_id: str
    route_id: str
    pattern_id: str
    stop_id: str
    sequence: int
    kind: EventKind
    earliest_at: float | None
    latest_at: float | None
    estimated_at: float | None
    support_ids: tuple[str, ...]
    method: str
    uncertainty_s: float | None
    confidence: Confidence
    accepted: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Measurement:
    measurement_id: str
    identity_id: str
    segment_id: str
    pattern_id: str
    origin_stop_id: str
    origin_sequence: int
    destination_stop_id: str
    destination_sequence: int
    event_ids: tuple[str, ...]
    duration_min_s: float | None
    duration_max_s: float | None
    estimated_duration_s: float | None
    waiting_time_s: float | None
    walking_time_s: float | None
    accepted: bool
    confidence: Confidence
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Rejection:
    subject_id: str
    stage: str
    reason: str
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconstructionResult:
    algorithm_version: str
    catalog_sha256: str
    parameters: Parameters
    snapshots: tuple[ProviderSnapshot, ...]
    normalized: tuple[NormalizedObservation, ...]
    segments: tuple[TrajectorySegment, ...]
    projections: tuple[Projection, ...]
    events: tuple[StopEvent, ...]
    measurements: tuple[Measurement, ...]
    rejections: tuple[Rejection, ...]
    evidence: tuple[IdentityEvidence, ...]
    input_order_warnings: tuple[str, ...]
    targets: tuple = ()
    real_operational_validation: bool = False
    algorithm_sha256: str = ""
