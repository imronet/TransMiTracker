"""Bounded GTFS-only itinerary search, independent of widgets and profile storage."""

import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from transmitracker.catalog import CatalogError
from transmitracker.catalog.common import BOGOTA
from transmitracker.catalog.queries import Catalog
from transmitracker.profiles.contracts import Issue, Result, failure
from transmitracker.profiles.models import Profile, ProfileKind
from transmitracker.profiles.services import CatalogService

DISCLAIMER = "Planificación basada en GTFS estático. No es una predicción en tiempo real."


@dataclass(frozen=True)
class ScheduledStep:
    leg_index: int
    route_id: str
    pattern_id: str
    origin_stop_id: str
    origin_sequence: int
    destination_stop_id: str
    destination_sequence: int
    origin_platform_id: str
    route_name: str
    origin_name: str
    destination_name: str
    ready_at: str
    boarding_at: str
    arrival_at: str
    service_date: str
    trip_id: str
    time_basis: str
    scheduled_wait_seconds: float
    transfer_walk_minutes: int
    transfer_buffer_minutes: int


@dataclass(frozen=True)
class StaticPlan:
    profile_id: str
    kind: str
    planning_date: str
    departure_at: str
    arrival_at: str
    arrival_with_margin_at: str
    arrival_deadline_at: str | None
    initial_walk_minutes: int
    final_walk_minutes: int
    safety_margin_minutes: int
    steps: tuple[ScheduledStep, ...]
    search_start: str
    boarding_horizon_end: str
    window_minutes: int
    catalog_sha256: str
    catalog_imported_at: str
    basis: str = "static_gtfs_itinerary_not_realtime_prediction"
    spatial_connections_verified: bool = False
    disclaimer: str = DISCLAIMER


class StaticPlanner:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog

    def plan(
        self, profile: Profile, planning_day: date, departure_clock: time | None = None
    ) -> Result[StaticPlan]:
        checked = CatalogService(self.catalog).validate_structure(profile)
        if not checked.ok:
            return checked
        if type(planning_day) is not date:
            return failure("INVALID_PLANNING_DATE", "planning_date", "Choose a local civil date")
        if planning_day.weekday() not in profile.active_weekdays:
            return failure("PROFILE_INACTIVE_DAY", "active_weekdays", "Inactive departure date")
        midnight = datetime.combine(planning_day, time(), BOGOTA)
        window = timedelta(minutes=profile.departure_window_minutes)
        initial = timedelta(minutes=profile.initial_walk_minutes)
        final = timedelta(minutes=profile.final_walk_minutes + profile.safety_margin_minutes)
        deadline = None
        if profile.kind == ProfileKind.TO_WORK:
            deadline = datetime.combine(
                planning_day + timedelta(days=profile.arrival_day_offset),
                profile.arrival_deadline,
                BOGOTA,
            )
            start = max(midnight, deadline - window)
            end = deadline
            requested_departure = None
        else:
            clock = departure_clock if departure_clock is not None else profile.usual_departure
            if clock is None:
                return failure(
                    "DEPARTURE_TIME_REQUIRED", "departure_clock", "Provide a departure time"
                )
            if not isinstance(clock, time) or clock.tzinfo is not None:
                return failure("INVALID_CLOCK", "departure_clock", "Use a local wall clock")
            requested_departure = datetime.combine(planning_day, clock, BOGOTA)
            start, end = requested_departure, requested_departure + window
        query_start = start + initial
        if query_start > end or (deadline and start.date() != planning_day):
            return failure(
                "HORIZON_INSUFFICIENT",
                "departure_window_minutes",
                "No departure on selected date within this horizon",
            )
        minutes = max(1, math.ceil((end - query_start).total_seconds() / 60))
        options, uncertain = [], False
        try:
            for index, leg in enumerate(profile.legs):
                rows = self.catalog.scheduled_connections(leg, query_start, window_minutes=minutes)
                rows = [r for r in rows if datetime.fromisoformat(r["availability_from"]) <= end]
                exact = [
                    r for r in rows if r["boarding_at"] is not None and r["arrival_at"] is not None
                ]
                uncertain |= len(exact) != len(rows)
                if not exact:
                    if rows:
                        return failure(
                            "SCHEDULE_TIME_UNRESOLVED",
                            f"legs.{index}",
                            "Only unresolved frequency or missing times",
                        )
                    unresolved = self._missing_boarding(profile, query_start, end, (index,))
                    if unresolved is not None:
                        return unresolved
                    # Diagnose a bounded miss using the same calendar/query machinery;
                    # these wider alternatives are never selected as a recommendation.
                    probe_start = midnight if deadline else query_start
                    probe = self.catalog.scheduled_connections(
                        leg, probe_start, window_minutes=1440
                    )
                    relevant = (
                        [
                            r
                            for r in probe
                            if datetime.fromisoformat(r["availability_from"]) < deadline
                        ]
                        if deadline
                        else probe
                    )
                    code = "HORIZON_INSUFFICIENT" if relevant else "NO_SCHEDULED_SERVICE"
                    return failure(
                        code, f"legs.{index}", "No explicit boarding within the bounded search"
                    )
                options.append(exact)
        except (CatalogError, ValueError):
            return failure("LEG_SERVICE_INVALID", "legs", "Incompatible static selection")
        # Reverse dynamic search. Suffix minima retain the earliest final arrival
        # among all boardings after each transfer-ready time, including overtaking.
        chains = [
            (r,)
            for r in options[-1]
            if not deadline or datetime.fromisoformat(r["arrival_at"]) + final <= deadline
        ]
        if not chains:
            unresolved = self._missing_boarding(profile, query_start, end)
            if unresolved is not None:
                return unresolved
            return failure(
                "ARRIVAL_DEADLINE_EXCEEDED",
                "arrival_deadline",
                "All explicit arrivals miss the configured deadline",
            )
        for index in range(len(options) - 2, -1, -1):
            chains.sort(key=lambda c: (c[0]["boarding_at"], c[-1]["arrival_at"]))
            boardings = [datetime.fromisoformat(c[0]["boarding_at"]) for c in chains]
            best = [None] * len(chains)
            for i in range(len(chains) - 1, -1, -1):
                best[i] = min(
                    (chains[i], best[i + 1]) if i + 1 < len(chains) else (chains[i],),
                    key=lambda c: (c[-1]["arrival_at"], c[0]["boarding_at"]),
                )
            transfer = profile.transfers[index]
            delay = timedelta(minutes=transfer.walking_minutes + transfer.buffer_minutes)
            combined, within_horizon = [], False
            for row in options[index]:
                ready = datetime.fromisoformat(row["arrival_at"]) + delay
                within_horizon |= ready <= end
                position = bisect_left(boardings, ready)
                if position < len(best):
                    combined.append((row, *best[position]))
            if not combined:
                unresolved = self._missing_boarding(profile, query_start, end)
                if unresolved is not None:
                    return unresolved
                code = "TRANSFER_INCOMPATIBLE" if within_horizon else "HORIZON_INSUFFICIENT"
                if uncertain:
                    code = "SCHEDULE_TIME_UNRESOLVED"
                return failure(
                    code, f"transfers.{index}", "No compatible timed transfer within the search"
                )
            chains = combined
        if deadline:
            chains = [
                c
                for c in chains
                if (datetime.fromisoformat(c[0]["boarding_at"]) - initial).date() == planning_day
            ]
            if not chains:
                return failure(
                    "HORIZON_INSUFFICIENT",
                    "planning_date",
                    "No home departure on selected civil date",
                )
            chosen = max(
                chains,
                key=lambda c: (
                    datetime.fromisoformat(c[0]["boarding_at"]),
                    -datetime.fromisoformat(c[-1]["arrival_at"]).timestamp(),
                ),
            )
            departure = datetime.fromisoformat(chosen[0]["boarding_at"]) - initial
        else:
            chosen = min(chains, key=lambda c: (c[-1]["arrival_at"], c[0]["boarding_at"]))
            departure = requested_departure
        ready, steps = departure + initial, []
        for index, (row, leg) in enumerate(zip(chosen, profile.legs, strict=True)):
            walk = buffer = 0
            if index:
                transfer = profile.transfers[index - 1]
                walk, buffer = transfer.walking_minutes, transfer.buffer_minutes
                ready += timedelta(minutes=walk + buffer)
            boarding = datetime.fromisoformat(row["boarding_at"])
            steps.append(
                ScheduledStep(
                    index,
                    leg.route_id,
                    leg.pattern_id,
                    leg.origin_stop_id,
                    leg.origin_sequence,
                    leg.destination_stop_id,
                    leg.destination_sequence,
                    row["origin_platform_id"],
                    row["route_name"],
                    row["origin_name"],
                    row["destination_name"],
                    ready.isoformat(),
                    row["boarding_at"],
                    row["arrival_at"],
                    row["service_date"],
                    row["trip_id"],
                    row["time_basis"],
                    (boarding - ready).total_seconds(),
                    walk,
                    buffer,
                )
            )
            ready = datetime.fromisoformat(row["arrival_at"])
        info = self.catalog.info()
        warnings = list(checked.warnings)
        if uncertain:
            warnings.append(
                Issue(
                    "UNRESOLVED_ALTERNATIVES_EXCLUDED",
                    "schedule",
                    "Only explicit alternatives participate in the optimum",
                )
            )
        return Result(
            data=StaticPlan(
                profile.profile_id,
                profile.kind.value,
                planning_day.isoformat(),
                departure.isoformat(),
                (ready + timedelta(minutes=profile.final_walk_minutes)).isoformat(),
                (ready + final).isoformat(),
                deadline.isoformat() if deadline else None,
                profile.initial_walk_minutes,
                profile.final_walk_minutes,
                profile.safety_margin_minutes,
                tuple(steps),
                start.isoformat(),
                end.isoformat(),
                profile.departure_window_minutes,
                info["sha256"],
                info["imported_at"],
                spatial_connections_verified=not profile.transfers,
            ),
            warnings=tuple(warnings),
        )

    def _missing_boarding(self, profile, when, until, indices=None):
        for index in indices if indices is not None else range(len(profile.legs)):
            if self.catalog.has_unresolved_boarding(profile.legs[index], when, until):
                field = f"legs.{index}"
                return Result(
                    errors=(
                        Issue(
                            "SCHEDULE_TIME_UNRESOLVED",
                            field,
                            "Active service has incomplete boarding times",
                        ),
                    ),
                    warnings=(
                        Issue(
                            "SCHEDULE_WINDOW_UNVERIFIED",
                            field,
                            "Missing times prevent confirming membership in the selected window",
                        ),
                    ),
                )
        return None
