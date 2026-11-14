"""Published synthetic schedules only; no GPS, network or invented waits."""

from dataclasses import replace
from datetime import date, datetime, time, timedelta

import pytest
from test_catalog import make_catalog_tables, write_zip

from transmitracker.catalog.common import BOGOTA
from transmitracker.catalog.importer import import_catalog
from transmitracker.catalog.queries import Catalog
from transmitracker.profiles.models import Leg, Profile, ProfileKind, Transfer
from transmitracker.profiles.planning import StaticPlanner


def planning_tables():
    tables = make_catalog_tables()

    def add(identity, route, stops):
        tables["trips.txt"][1].append([identity, route, "WK", 0, "SH1"])
        for i, (stop, clock) in enumerate(stops, 1):
            tables["stop_times.txt"][1].append([identity, i * 10, stop, clock, clock, 0, 0])

    add(
        "SLOW",
        "001",
        [("0006", "08:00:00"), ("0001", "08:10:00"), ("0003", "08:30:00"), ("0004", "09:10:00")],
    )
    add(
        "FAST",
        "001",
        [("0006", "08:10:00"), ("0001", "08:15:00"), ("0003", "08:20:00"), ("0004", "08:25:00")],
    )
    add(
        "LATE",
        "001",
        [("0006", "08:20:00"), ("0001", "08:30:00"), ("0003", "08:40:00"), ("0004", "09:30:00")],
    )
    tables["routes.txt"][1].extend(
        [["010", "SYN10", "Synthetic transfer", 3], ["011", "SYN11", "Synthetic final", 3]]
    )
    add("L2", "010", [("0001", "08:20:00"), ("0003", "08:30:00"), ("0004", "08:45:00")])
    add("L2_EARLY", "010", [("0001", "08:16:00"), ("0003", "08:21:00"), ("0004", "08:35:00")])
    add("L3", "011", [("0003", "08:35:00"), ("0004", "08:45:00")])
    return tables


@pytest.fixture(scope="module")
def planning_catalog_path(tmp_path_factory):
    root = tmp_path_factory.mktemp("static-planning")
    path = root / "catalog.sqlite3"
    import_catalog(write_zip(root / "synthetic.zip", planning_tables()), path)
    return path


@pytest.fixture
def catalog(planning_catalog_path):
    with Catalog(planning_catalog_path) as instance:
        yield instance


def leg_for(catalog, trip="MAIN", origin="0006", destination="0004", a=10, b=40):
    row = catalog.connection.execute("SELECT * FROM trips WHERE trip_id=?", (trip,)).fetchone()
    return Leg(origin, row["route_id"], row["pattern_id"], row["direction_id"], a, destination, b)


def work_profile(catalog):
    return Profile(
        "SYNTHETIC_PLAN",
        ProfileKind.TO_WORK,
        catalog.info()["sha256"],
        (leg_for(catalog),),
        (),
        5,
        2,
        time(8, 30),
        time(7),
        (0, 1, 2, 3, 4),
        safety_margin_minutes=3,
    )


def test_direct_latest_viable_departure_has_no_implicit_safety_buffer(catalog):
    profile = work_profile(catalog)
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9))
    assert result.ok, result.to_dict()
    plan = result.data
    assert plan.departure_at == "2026-11-09T08:05:00-05:00"
    assert plan.steps[0].trip_id == "FAST"
    assert plan.steps[0].boarding_at == "2026-11-09T08:10:00-05:00"
    assert plan.arrival_at == "2026-11-09T08:27:00-05:00"
    assert plan.arrival_with_margin_at == plan.arrival_deadline_at == "2026-11-09T08:30:00-05:00"
    assert plan.steps[0].scheduled_wait_seconds == 0
    assert plan.safety_margin_minutes == 3


def test_return_uses_explicit_departure_and_can_choose_later_faster_trip(catalog):
    profile = replace(
        work_profile(catalog),
        kind=ProfileKind.TO_HOME,
        initial_walk_minutes=0,
        arrival_deadline=time(1),
        usual_departure=time(7, 55),
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9))
    assert result.ok
    assert result.data.steps[0].trip_id == "FAST"  # SLOW boards sooner but arrives later.
    assert result.data.departure_at == "2026-11-09T07:55:00-05:00"
    assert result.data.steps[0].scheduled_wait_seconds == 900
    assert result.data.arrival_deadline_at is None
    assert result.data.arrival_with_margin_at == "2026-11-09T08:30:00-05:00"


@pytest.mark.parametrize("count", [2, 3])
def test_temporally_compatible_transfers_with_all_walks_and_buffers(catalog, count):
    first = leg_for(catalog, destination="0001", b=20)
    second = leg_for(
        catalog, "L2", "0001", "0004" if count == 2 else "0003", 10, 30 if count == 2 else 20
    )
    legs = (
        (first, second)
        if count == 2
        else (first, second, leg_for(catalog, "L3", "0003", "0004", 10, 20))
    )
    profile = replace(
        work_profile(catalog),
        legs=legs,
        transfers=(Transfer(2, 3),) * (count - 1),
        arrival_deadline=time(8, 50),
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9))
    assert result.ok, result.to_dict()
    plan = result.data
    assert plan.departure_at == "2026-11-09T08:05:00-05:00"
    assert plan.steps[1].trip_id == "L2"  # 08:16 is too soon for 2+3 minute transfer.
    assert plan.arrival_with_margin_at == "2026-11-09T08:50:00-05:00"
    assert not plan.spatial_connections_verified
    assert all(s.scheduled_wait_seconds >= 0 for s in plan.steps)
    assert len(result.warnings) == count - 1


def test_no_transfer_is_fabricated(catalog):
    profile = replace(
        work_profile(catalog),
        legs=(leg_for(catalog), leg_for(catalog, "L3", "0003", "0004", 10, 20)),
        transfers=(Transfer(16, 0),),
        arrival_deadline=time(9, 40),
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9))
    assert not result.ok and result.errors[0].code == "TRANSFER_INCOMPATIBLE"


def test_walk_and_margin_can_make_all_explicit_arrivals_late(catalog):
    result = StaticPlanner(catalog).plan(
        replace(work_profile(catalog), arrival_deadline=time(8, 24)), date(2026, 11, 9)
    )
    assert not result.ok and result.errors[0].code == "ARRIVAL_DEADLINE_EXCEEDED"


def test_inactive_profile_and_no_service_are_distinct(catalog):
    planner = StaticPlanner(catalog)
    assert (
        planner.plan(work_profile(catalog), date(2026, 11, 8)).errors[0].code
        == "PROFILE_INACTIVE_DAY"
    )
    profile = replace(work_profile(catalog), active_weekdays=tuple(range(7)))
    assert planner.plan(profile, date(2026, 11, 8)).errors[0].code == "NO_SCHEDULED_SERVICE"


def test_calendar_removed_and_added_services(catalog):
    planner = StaticPlanner(catalog)
    assert (
        planner.plan(work_profile(catalog), date(2026, 11, 12)).errors[0].code
        == "NO_SCHEDULED_SERVICE"
    )
    profile = replace(
        work_profile(catalog),
        legs=(leg_for(catalog, "SPECIAL", "0001", "0004", 10, 20),),
        initial_walk_minutes=0,
        arrival_deadline=time(8, 15),
    )
    result = planner.plan(profile, date(2026, 11, 12))
    assert result.ok and result.data.steps[0].service_date == "2026-11-12"


def test_midnight_gtfs_25h_and_arrival_day_offset(catalog):
    profile = replace(
        work_profile(catalog),
        legs=(leg_for(catalog, "NIGHT", "0001", "0004", 10, 20),),
        initial_walk_minutes=90,
        arrival_deadline=time(1, 30),
        arrival_day_offset=1,
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9))
    assert result.ok, result.to_dict()
    assert result.data.departure_at == "2026-11-09T23:30:00-05:00"
    assert result.data.steps[0].boarding_at == "2026-11-10T01:00:00-05:00"
    assert result.data.steps[0].service_date == "2026-11-09"
    assert result.data.arrival_with_margin_at == "2026-11-10T01:15:00-05:00"


def test_return_crosses_midnight_using_previous_gtfs_service_date(catalog):
    profile = replace(
        work_profile(catalog),
        kind=ProfileKind.TO_HOME,
        legs=(leg_for(catalog, "NIGHT", "0001", "0004", 10, 20),),
        initial_walk_minutes=0,
        usual_departure=time(0, 45),
        active_weekdays=tuple(range(7)),
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 10))
    assert result.ok and result.data.steps[0].service_date == "2026-11-09"
    assert result.data.steps[0].boarding_at == "2026-11-10T01:00:00-05:00"


def test_frequencies_without_exact_times_never_become_point_recommendations(catalog):
    profile = replace(
        work_profile(catalog),
        legs=(leg_for(catalog, "FREQ_APPROX", "0001", "0004", 10, 20),),
        arrival_deadline=time(23, 59),
        initial_walk_minutes=0,
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9))
    assert not result.ok and result.errors[0].code == "SCHEDULE_TIME_UNRESOLVED"


def test_exact_frequency_search_enumerates_later_boardings(catalog):
    profile = replace(
        work_profile(catalog),
        legs=(leg_for(catalog, "FREQ_EXACT", "0001", "0004", 10, 20),),
        arrival_deadline=time(8, 25),
        initial_walk_minutes=0,
        final_walk_minutes=0,
        safety_margin_minutes=0,
        departure_window_minutes=60,
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9))
    assert result.ok and result.data.departure_at == "2026-11-09T08:10:00-05:00"
    assert result.data.steps[0].time_basis == "frequency_exact"


def test_incompatible_catalog_horizon_and_missing_return_time(catalog):
    planner = StaticPlanner(catalog)
    profile = work_profile(catalog)
    assert (
        planner.plan(replace(profile, catalog_sha256="f" * 64), date(2026, 11, 9)).errors[0].code
        == "CATALOG_VERSION_MISMATCH"
    )
    assert (
        planner.plan(replace(profile, departure_window_minutes=1), date(2026, 11, 9)).errors[0].code
        == "HORIZON_INSUFFICIENT"
    )
    assert (
        planner.plan(replace(profile, kind=ProfileKind.TO_HOME), date(2026, 11, 9)).errors[0].code
        == "DEPARTURE_TIME_REQUIRED"
    )


def test_49h_trip_keeps_friday_service_date_on_civil_sunday(catalog):
    profile = replace(
        work_profile(catalog),
        kind=ProfileKind.TO_HOME,
        legs=(leg_for(catalog, "NIGHT49", "0001", "0004", 10, 20),),
        initial_walk_minutes=0,
        active_weekdays=tuple(range(7)),
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 15), time(0, 45))
    assert result.ok
    assert result.data.steps[0].trip_id == "NIGHT49"
    assert result.data.steps[0].service_date == "2026-11-13"
    assert result.data.steps[0].boarding_at == "2026-11-15T01:00:00-05:00"


def test_selected_three_leg_itinerary_matches_exact_active_gtfs_rows(catalog):
    profile = replace(
        work_profile(catalog),
        legs=(
            leg_for(catalog, destination="0001", b=20),
            leg_for(catalog, "L2", "0001", "0003", 10, 20),
            leg_for(catalog, "L3", "0003", "0004", 10, 20),
        ),
        transfers=(Transfer(2, 3), Transfer(2, 3)),
        arrival_deadline=time(8, 50),
    )
    plan = StaticPlanner(catalog).plan(profile, date(2026, 11, 9)).data
    for step in plan.steps:
        trip = catalog.connection.execute(
            "SELECT * FROM trips WHERE trip_id=?", (step.trip_id,)
        ).fetchone()
        service_date = date.fromisoformat(step.service_date)
        assert trip["service_id"] in catalog.active_services(service_date)
        assert (trip["route_id"], trip["pattern_id"]) == (step.route_id, step.pattern_id)
        for stop_id, sequence, column, timestamp in (
            (step.origin_platform_id, step.origin_sequence, "departure", step.boarding_at),
            (step.destination_stop_id, step.destination_sequence, "arrival", step.arrival_at),
        ):
            row = catalog.connection.execute(
                "SELECT * FROM stop_times WHERE trip_pk=? AND stop_id=? AND sequence=?",
                (trip["trip_pk"], stop_id, sequence),
            ).fetchone()
            expected = datetime.combine(service_date, time(), BOGOTA) + timedelta(
                seconds=row[column]
            )
            assert timestamp == expected.isoformat()
        assert datetime.fromisoformat(step.ready_at) <= datetime.fromisoformat(step.boarding_at)


def test_search_window_bounds_boardings_not_estimated_waits(catalog):
    profile = replace(
        work_profile(catalog),
        kind=ProfileKind.TO_HOME,
        initial_walk_minutes=0,
        departure_window_minutes=5,
        usual_departure=time(7, 55),
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9), time(8, 5))
    assert result.ok
    assert result.data.steps[0].trip_id == "FAST"
    assert result.data.steps[0].scheduled_wait_seconds == 300
    assert result.data.arrival_at > result.data.boarding_horizon_end
    assert result.data.departure_at == "2026-11-09T08:05:00-05:00"  # Overrides usual.


def test_initial_walk_cannot_be_used_to_bypass_horizon(catalog):
    profile = replace(
        work_profile(catalog),
        kind=ProfileKind.TO_HOME,
        initial_walk_minutes=6,
        departure_window_minutes=5,
    )
    result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9), time(8, 5))
    assert result.errors[0].code == "HORIZON_INSUFFICIENT"
