from dataclasses import dataclass, fields
from datetime import time
from enum import Enum

from transmitracker.profiles.contracts import Issue, Result


class ProfileKind(str, Enum):
    TO_WORK = "home_to_work"
    TO_HOME = "work_to_home"


@dataclass(frozen=True)
class Leg:
    origin_stop_id: str
    route_id: str
    pattern_id: str
    direction_id: int | None
    origin_sequence: int
    destination_stop_id: str
    destination_sequence: int


@dataclass(frozen=True)
class Transfer:
    walking_minutes: int
    buffer_minutes: int = 0


@dataclass(frozen=True)
class Profile:
    profile_id: str
    kind: ProfileKind
    catalog_sha256: str
    legs: tuple[Leg, ...]
    transfers: tuple[Transfer, ...]
    initial_walk_minutes: int
    final_walk_minutes: int
    arrival_deadline: time | None
    notification_time: time
    active_weekdays: tuple[int, ...]
    safety_margin_minutes: int = 0
    arrival_day_offset: int = 0
    departure_window_minutes: int = 120
    usual_departure: time | None = None


@dataclass(frozen=True)
class StructuralStopChoice:
    stop_id: str
    name: str
    sequence: int
    parent_station: str | None
    platform_code: str | None


@dataclass(frozen=True)
class StructureCheck:
    profile_id: str
    catalog_sha256: str
    leg_count: int
    basis: str = "catalog_structure_without_service_date"
    expected_wait_minutes: float | None = None
    wait_basis: str = "unavailable_no_historical_estimate"


@dataclass(frozen=True)
class StopChoice:
    stop_id: str
    name: str
    code: str | None
    parent_station: str | None
    platform_code: str | None
    location_type: int


@dataclass(frozen=True)
class RouteChoice:
    route_id: str
    short_name: str
    long_name: str


@dataclass(frozen=True)
class PatternChoice:
    route_id: str
    direction_id: int | None
    pattern_id: str
    origin_platform_id: str
    origin_sequence: int
    service_dates: tuple[str, ...]
    next_boarding_at: str | None
    time_basis: str


@dataclass(frozen=True)
class DestinationChoice:
    stop_id: str
    name: str
    sequence: int
    parent_station: str | None
    service_date: str
    arrival_at: str | None
    time_basis: str


@dataclass(frozen=True)
class LegCheck:
    leg_index: int
    ready_at: str
    boarding_at: str | None
    scheduled_arrival_at: str | None
    service_date: str | None
    example_trip_id: str | None


@dataclass(frozen=True)
class ProfileCheck:
    profile_id: str
    catalog_sha256: str
    legs: tuple[LegCheck, ...]
    arrival_with_walk_and_margin: str | None
    spatial_connections_verified: bool
    basis: str = "static_schedule_validation_not_prediction"


def profile_from_dict(payload: dict) -> Result[Profile]:
    """Strict whitelist: credential/unknown fields are rejected, never persisted."""
    try:
        if not isinstance(payload, dict) or set(payload) - {f.name for f in fields(Profile)}:
            raise ValueError("Unknown profile fields")
        for name, cls in (("legs", Leg), ("transfers", Transfer)):
            if not isinstance(payload[name], list):
                raise ValueError(f"{name} must be an array")
            if any(
                not isinstance(v, dict) or set(v) - {f.name for f in fields(cls)}
                for v in payload[name]
            ):
                raise ValueError(f"Unknown fields in {name}")
        values = dict(payload)
        values.update(
            kind=ProfileKind(values["kind"]),
            legs=tuple(Leg(**v) for v in values["legs"]),
            transfers=tuple(Transfer(**v) for v in values["transfers"]),
            arrival_deadline=time.fromisoformat(values["arrival_deadline"])
            if values["arrival_deadline"]
            else None,
            notification_time=time.fromisoformat(values["notification_time"]),
            active_weekdays=tuple(values["active_weekdays"]),
            usual_departure=time.fromisoformat(values["usual_departure"])
            if values.get("usual_departure")
            else None,
        )
        return Result(data=Profile(**values))
    except (KeyError, TypeError, ValueError) as exc:
        return Result(errors=(Issue("INVALID_PAYLOAD", "profile", str(exc)),))
