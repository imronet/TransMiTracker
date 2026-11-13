"""Thin catalog facade and profile schedule validation, independent of GUI/CLI."""

import re
import sqlite3
from dataclasses import fields
from datetime import datetime, time, timedelta

from transmitracker.catalog import CatalogError
from transmitracker.catalog.common import BOGOTA, aware
from transmitracker.catalog.queries import Catalog
from transmitracker.profiles.contracts import Issue, Result, failure
from transmitracker.profiles.models import (
    DestinationChoice,
    Leg,
    LegCheck,
    PatternChoice,
    Profile,
    ProfileCheck,
    ProfileKind,
    RouteChoice,
    StopChoice,
    StructuralStopChoice,
    StructureCheck,
    Transfer,
)


def shape_errors(profile: Profile) -> tuple[Issue, ...]:
    errors = []

    def reject(code, field, message):
        errors.append(Issue(code, field, message))

    if not isinstance(profile, Profile):
        return (Issue("INVALID_MODEL", "profile", "Expected Profile"),)
    if (
        not isinstance(profile.profile_id, str)
        or not profile.profile_id
        or len(profile.profile_id) > 100
    ):
        reject("INVALID_ID", "profile_id", "A nonempty ID up to 100 characters is required")
    if not isinstance(profile.kind, ProfileKind):
        reject("INVALID_KIND", "kind", "Choose one of the two commute profiles")
    if not isinstance(profile.catalog_sha256, str) or not re.fullmatch(
        "[0-9a-f]{64}", profile.catalog_sha256
    ):
        reject("INVALID_CATALOG_HASH", "catalog_sha256", "Expected a SHA-256 catalog reference")
    if (
        not isinstance(profile.legs, tuple)
        or not 1 <= len(profile.legs) <= 3
        or any(not isinstance(v, Leg) for v in profile.legs)
    ):
        reject("LEG_COUNT", "legs", "Select one to three typed legs")
        return tuple(errors)
    if (
        not isinstance(profile.transfers, tuple)
        or any(not isinstance(v, Transfer) for v in profile.transfers)
        or len(profile.transfers) != max(0, len(profile.legs) - 1)
    ):
        reject(
            "TRANSFER_COUNT",
            "transfers",
            "Exactly one transfer specification per connection is required",
        )
    for name in (
        "initial_walk_minutes",
        "final_walk_minutes",
        "safety_margin_minutes",
        "departure_window_minutes",
    ):
        value = getattr(profile, name)
        low = 1 if name == "departure_window_minutes" else 0
        if type(value) is not int or not low <= value <= 1440:
            reject("INVALID_MINUTES", name, f"Expected integer minutes {low}..1440")
    if type(profile.arrival_day_offset) is not int or profile.arrival_day_offset not in (0, 1):
        reject("INVALID_DAY_OFFSET", "arrival_day_offset", "Choose same day or next day explicitly")
    if (
        not isinstance(profile.active_weekdays, tuple)
        or not profile.active_weekdays
        or any(type(v) is not int or not 0 <= v <= 6 for v in profile.active_weekdays)
        or len(set(profile.active_weekdays)) != len(profile.active_weekdays)
    ):
        reject(
            "INVALID_WEEKDAYS", "active_weekdays", "Use distinct weekdays 0=Monday through 6=Sunday"
        )
    for name in ("arrival_deadline", "notification_time"):
        value = getattr(profile, name)
        if name == "arrival_deadline" and profile.kind == ProfileKind.TO_HOME and value is None:
            continue
        if not isinstance(value, time) or value.tzinfo is not None:
            reject("INVALID_CLOCK", name, "Expected a local wall clock in America/Bogota")
    if profile.usual_departure is not None and (
        not isinstance(profile.usual_departure, time) or profile.usual_departure.tzinfo is not None
    ):
        reject("INVALID_CLOCK", "usual_departure", "Expected an optional local wall clock")
    if isinstance(profile.legs, tuple):
        for index, leg in enumerate(profile.legs):
            if not isinstance(leg, Leg):
                continue
            for name in ("origin_stop_id", "route_id", "pattern_id", "destination_stop_id"):
                if not isinstance(getattr(leg, name), str) or not getattr(leg, name):
                    reject("INVALID_ID", f"legs.{index}.{name}", "IDs must be nonempty strings")
            if leg.direction_id is not None and (
                type(leg.direction_id) is not int or leg.direction_id not in (0, 1)
            ):
                reject("INVALID_DIRECTION", f"legs.{index}.direction_id", "Use 0, 1 or unknown")
            if (
                any(
                    type(getattr(leg, name)) is not int or getattr(leg, name) < 0
                    for name in ("origin_sequence", "destination_sequence")
                )
                or leg.destination_sequence <= leg.origin_sequence
            ):
                reject(
                    "INVALID_SEQUENCE", f"legs.{index}", "Destination occurrence must follow origin"
                )
    if isinstance(profile.transfers, tuple):
        for index, transfer in enumerate(profile.transfers):
            if isinstance(transfer, Transfer):
                for field in fields(Transfer):
                    value = getattr(transfer, field.name)
                    if type(value) is not int or not 0 <= value <= 1440:
                        reject(
                            "INVALID_MINUTES",
                            f"transfers.{index}.{field.name}",
                            "Expected integer minutes 0..1440",
                        )
    return tuple(errors)


class CatalogService:
    """Each operation returns a versioned Result, not CLI text or widget values."""

    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self.sha256 = catalog.info()["sha256"]

    def _call(self, callback):
        try:
            return Result(data=callback())
        except (CatalogError, ValueError, TypeError, AttributeError) as exc:
            return failure("CATALOG_SELECTION_INVALID", "selection", str(exc))
        except (sqlite3.Error, OSError):
            return failure("CATALOG_UNAVAILABLE", "catalog", "Catalog could not be read")

    def search_stops(self, query: str, *, limit=20) -> Result[tuple[StopChoice, ...]]:
        if not isinstance(query, str):
            return failure("INVALID_QUERY", "query", "Expected text")
        return self._call(
            lambda: tuple(
                StopChoice(**{f.name: r[f.name] for f in fields(StopChoice)})
                for r in self.catalog.search_stops(query, limit=limit)
            )
        )

    def search_routes(self, query: str, *, limit=25):
        return self._call(
            lambda: tuple(
                RouteChoice(**row) for row in self.catalog.search_routes(query, limit=limit)
            )
        )

    def structural_patterns(self, route_id, origin=None):
        return self._call(
            lambda: tuple(
                PatternChoice(**row) for row in self.catalog.structural_patterns(route_id, origin)
            )
        )

    def structural_stops(self, pattern_id, origin_sequence=None):
        return self._call(
            lambda: tuple(
                StructuralStopChoice(**row)
                for row in self.catalog.structural_stops(pattern_id, origin_sequence)
            )
        )

    def structural_routes(self, origin):
        return self._call(
            lambda: tuple(RouteChoice(**row) for row in self.catalog.structural_routes(origin))
        )

    def validate_structure(self, profile: Profile):
        errors = shape_errors(profile)
        if errors:
            return Result(errors=errors)
        if profile.catalog_sha256 != self.sha256:
            return failure("CATALOG_VERSION_MISMATCH", "catalog_sha256", "Pinned catalog differs")
        for index, leg in enumerate(profile.legs):
            try:
                self.catalog.validate_leg_structure(leg)
            except CatalogError:
                return failure(
                    "LEG_STRUCTURE_INVALID",
                    f"legs.{index}",
                    "Route, direction, stops or sequence do not match the catalog",
                )
            except (sqlite3.Error, OSError):
                return failure("CATALOG_UNAVAILABLE", "catalog", "Catalog cannot be read")
        return Result(
            data=StructureCheck(profile.profile_id, self.sha256, len(profile.legs)),
            warnings=tuple(
                Issue(
                    "TRANSFER_PATH_UNVERIFIED",
                    f"transfers.{i}",
                    "User walking time preserved; path unverified",
                )
                for i in range(len(profile.transfers))
            ),
        )

    def routes(
        self, origin: str, when: datetime, *, window_minutes=120
    ) -> Result[tuple[RouteChoice, ...]]:
        return self._call(
            lambda: tuple(
                RouteChoice(**r)
                for r in self.catalog.routes_for_stop(origin, when, window_minutes=window_minutes)
            )
        )

    def patterns(
        self, origin: str, when: datetime, *, window_minutes=120
    ) -> Result[tuple[PatternChoice, ...]]:
        def operation():
            return tuple(
                PatternChoice(
                    **{
                        f.name: tuple(r[f.name]) if f.name == "service_dates" else r[f.name]
                        for f in fields(PatternChoice)
                    }
                )
                for r in self.catalog.options(origin, when, window_minutes=window_minutes)
            )

        return self._call(operation)

    def destinations(
        self, leg: Leg, when: datetime, *, window_minutes=120
    ) -> Result[tuple[DestinationChoice, ...]]:
        return self._call(
            lambda: tuple(
                DestinationChoice(**{f.name: r[f.name] for f in fields(DestinationChoice)})
                for r in self.catalog.destinations(
                    leg.origin_stop_id,
                    leg.route_id,
                    leg.direction_id,
                    leg.pattern_id,
                    when,
                    origin_sequence=leg.origin_sequence,
                    window_minutes=window_minutes,
                )
            )
        )

    def validate(self, profile: Profile, departure_at: datetime) -> Result[ProfileCheck]:
        errors = shape_errors(profile)
        if errors:
            return Result(errors=errors)
        if profile.catalog_sha256 != self.sha256:
            return failure(
                "CATALOG_VERSION_MISMATCH",
                "catalog_sha256",
                "Profile is pinned to a different catalog; preview a migration",
            )
        try:
            departure_at = aware(departure_at)
        except (ValueError, AttributeError):
            return failure(
                "INVALID_DATETIME", "departure_at", "Provide a timezone-aware departure time"
            )
        if departure_at.weekday() not in profile.active_weekdays:
            return failure(
                "PROFILE_INACTIVE_DAY",
                "active_weekdays",
                "Profile is inactive on the requested civil departure day",
            )
        ready = departure_at + timedelta(minutes=profile.initial_walk_minutes)
        checks, warnings = [], []
        for index, leg in enumerate(profile.legs):
            if index:
                transfer = profile.transfers[index - 1]
                ready += timedelta(minutes=transfer.walking_minutes + transfer.buffer_minutes)
                warnings.append(
                    Issue(
                        "TRANSFER_PATH_UNVERIFIED",
                        f"transfers.{index - 1}",
                        "User walking/buffer time is preserved; no pedestrian connection has been verified, even within one station",
                    )
                )
            # Catalog supplies calendar, pattern, platform, occurrence and downstream rules.
            try:
                destination = self.catalog.validate_destination(
                    leg.origin_stop_id,
                    leg.route_id,
                    leg.direction_id,
                    leg.pattern_id,
                    ready,
                    leg.destination_stop_id,
                    destination_sequence=leg.destination_sequence,
                    origin_sequence=leg.origin_sequence,
                    window_minutes=profile.departure_window_minutes,
                )
            except CatalogError as exc:
                return Result(
                    errors=(Issue("LEG_SERVICE_INVALID", f"legs.{index}", str(exc)),),
                    warnings=tuple(warnings),
                )
            except (sqlite3.Error, OSError):
                return failure("CATALOG_UNAVAILABLE", "catalog", "Catalog could not be read")
            if destination["arrival_at"] is None or destination["boarding_at"] is None:
                return Result(
                    errors=(
                        Issue(
                            "SCHEDULE_TIME_UNRESOLVED",
                            f"legs.{index}",
                            "A frequency window or missing time cannot prove a timed connection",
                        ),
                    ),
                    warnings=tuple(warnings),
                )
            arrival = datetime.fromisoformat(destination["arrival_at"])
            checks.append(
                LegCheck(
                    index,
                    ready.isoformat(),
                    destination["boarding_at"],
                    arrival.isoformat(),
                    destination["service_date"],
                    destination["example_trip_id"],
                )
            )
            ready = arrival
        finish = ready + timedelta(
            minutes=profile.final_walk_minutes + profile.safety_margin_minutes
        )
        deadline = datetime.combine(
            departure_at.date() + timedelta(days=profile.arrival_day_offset),
            profile.arrival_deadline or time.max,
            BOGOTA,
        )
        if profile.kind == ProfileKind.TO_WORK and finish > deadline:
            return Result(
                errors=(
                    Issue(
                        "ARRIVAL_DEADLINE_EXCEEDED",
                        "arrival_deadline",
                        "Scheduled arrival plus final walk and safety margin exceeds the configured deadline",
                    ),
                ),
                warnings=tuple(warnings),
            )
        notice = datetime.combine(departure_at.date(), profile.notification_time, BOGOTA)
        if notice > departure_at:
            warnings.append(
                Issue(
                    "NOTICE_AFTER_DEPARTURE",
                    "notification_time",
                    "The configured notice is later than this departure; no notification is scheduled",
                )
            )
        return Result(
            data=ProfileCheck(
                profile.profile_id,
                self.sha256,
                tuple(checks),
                finish.isoformat(),
                not profile.transfers,
            ),
            warnings=tuple(warnings),
        )
