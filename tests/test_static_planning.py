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
    tables["routes.txt"][1].append(["012", "SYN12", "Synthetic seconds", 3])
    add("EVENING_EARLY", "012", [("0006", "17:30:20"), ("0004", "17:40:00")])
    add("EVENING_LATE", "012", [("0006", "17:31:00"), ("0004", "17:41:00")])
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


def incomplete_catalog(tmp_path, mode="missing", prior="07:55:00", after="08:30:00"):
    """An inactive reference preserves structure; only the tested alternative is active."""
    tables = make_catalog_tables()
    tables["trips.txt"][1][:] = [["MAIN", "001", "SLEEP", 0, "SH1"]]
    tables["stop_times.txt"][1][:] = [
        ["MAIN", 10, "0006", prior, prior, 0, 0],
        ["MAIN", 20, "0001", "08:10:00", "08:10:00", 0, 0],
        ["MAIN", 30, "0004", after, after, 0, 0],
    ]
    tables["frequencies.txt"][1].clear()
    tables["calendar.txt"][1].append(["SLEEP", 0, 0, 0, 0, 0, 0, 0, "20260101", "20261231"])
    if mode == "inactive_calendar":
        tables["calendar.txt"][1][0][1] = 0  # Monday.
    service = "EX" if mode == "added_exception" else "WK"
    for identity, clock in (("INCOMPLETE", ""), ("EXPLICIT", "08:10:00")):
        if (mode == "explicit" and not clock) or (mode != "mixed" and mode != "explicit" and clock):
            continue
        route = "002" if mode == "absent" else "001"
        tables["trips.txt"][1].append([identity, route, service, 0, "SH1"])
        tables["stop_times.txt"][1].extend(
            [
                [identity, 10, "0006", prior, prior, 0, 0],
                [identity, 20, "0001", clock, clock, 1 if mode == "pickup_denied" else 0, 0],
                [identity, 30, "0004", after, after, 0, 1 if mode == "dropoff_denied" else 0],
            ]
        )
    if mode.startswith("frequency"):
        start, end = {
            "frequency": ("08:00:00", "08:10:00"),
            "frequency_future": ("09:00:00", "09:10:00"),
            "frequency_overnight": ("25:00:00", "25:20:00"),
        }[mode]
        tables["frequencies.txt"][1].append(["INCOMPLETE", start, end, 600, 1])
    path = tmp_path / "incomplete.sqlite3"
    import_catalog(write_zip(tmp_path / "incomplete.zip", tables), path)
    return Catalog(path)


def incomplete_profile(catalog):
    return replace(
        work_profile(catalog),
        legs=(leg_for(catalog, "MAIN", "0001", "0004", 20, 30),),
        initial_walk_minutes=0,
        final_walk_minutes=0,
        safety_margin_minutes=0,
        active_weekdays=tuple(range(7)),
        departure_window_minutes=60,
    )


@pytest.mark.parametrize(
    "mode,day,code",
    [
        ("missing", date(2026, 11, 9), "SCHEDULE_TIME_UNRESOLVED"),
        ("absent", date(2026, 11, 9), "NO_SCHEDULED_SERVICE"),
        ("inactive_calendar", date(2026, 11, 9), "NO_SCHEDULED_SERVICE"),
        ("removed_exception", date(2026, 11, 12), "NO_SCHEDULED_SERVICE"),
        ("added_exception", date(2026, 11, 12), "SCHEDULE_TIME_UNRESOLVED"),
        ("pickup_denied", date(2026, 11, 9), "NO_SCHEDULED_SERVICE"),
        ("dropoff_denied", date(2026, 11, 9), "NO_SCHEDULED_SERVICE"),
        ("explicit", date(2026, 11, 9), None),
        ("mixed", date(2026, 11, 9), None),
    ],
)
def test_missing_origin_times_are_distinct_from_absent_active_service(tmp_path, mode, day, code):
    with incomplete_catalog(tmp_path, mode) as catalog:
        profile = incomplete_profile(catalog)
        before = catalog.options(
            "0001", datetime.combine(day, time(7, 30), BOGOTA), window_minutes=60
        )
        result = StaticPlanner(catalog).plan(profile, day)
        assert (
            catalog.options("0001", datetime.combine(day, time(7, 30), BOGOTA), window_minutes=60)
            == before
        )
        if code:
            assert not result.ok and result.data is None
            assert result.errors[0].code == code
            assert bool(result.warnings) == (code == "SCHEDULE_TIME_UNRESOLVED")
            if result.warnings:
                assert result.warnings[0].code == "SCHEDULE_WINDOW_UNVERIFIED"
        else:
            assert result.ok
            assert result.data.steps[0].trip_id == "EXPLICIT"
            assert result.data.steps[0].boarding_at == f"{day.isoformat()}T08:10:00-05:00"


@pytest.mark.parametrize("prior,after", [("07:00:00", "07:15:00"), ("09:00:00", "09:15:00")])
def test_known_neighbor_times_exclude_missing_departure_outside_window(tmp_path, prior, after):
    with incomplete_catalog(tmp_path, prior=prior, after=after) as catalog:
        result = StaticPlanner(catalog).plan(incomplete_profile(catalog), date(2026, 11, 9))
        assert result.errors[0].code == "NO_SCHEDULED_SERVICE"
        assert result.data is None


def test_no_neighbor_times_cannot_establish_membership_in_a_window(tmp_path):
    with incomplete_catalog(tmp_path, prior="", after="") as catalog:
        result = StaticPlanner(catalog).plan(incomplete_profile(catalog), date(2026, 11, 9))
        assert result.errors[0].code == "SCHEDULE_TIME_UNRESOLVED"
        assert result.warnings[0].code == "SCHEDULE_WINDOW_UNVERIFIED"
        assert result.data is None


def test_missing_time_diagnostic_uses_previous_gtfs_date_and_exact_horizon(tmp_path):
    with incomplete_catalog(tmp_path, prior="25:00:45", after="25:20:00") as catalog:
        profile = replace(
            incomplete_profile(catalog),
            kind=ProfileKind.TO_HOME,
            initial_walk_minutes=0,
            departure_window_minutes=1,
        )
        # No Sunday service, and Monday's >24h trip is still in the future.
        result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9), time(1))
        assert result.errors[0].code == "NO_SCHEDULED_SERVICE"
        # Friday 25h service is active on Saturday's civil date, despite Saturday
        # being inactive in calendar. A rounded minute must not include 01:00:45.
        result = StaticPlanner(catalog).plan(profile, date(2026, 11, 14), time(0, 59, 30))
        assert result.errors[0].code == "NO_SCHEDULED_SERVICE"
        assert not result.warnings
        result = StaticPlanner(catalog).plan(profile, date(2026, 11, 14), time(1))
        assert result.errors[0].code == "SCHEDULE_TIME_UNRESOLVED"
        assert result.data is None


@pytest.mark.parametrize(
    "mode,code",
    [("frequency", "SCHEDULE_TIME_UNRESOLVED"), ("frequency_future", "NO_SCHEDULED_SERVICE")],
)
def test_missing_frequency_offset_does_not_reuse_template_clock(tmp_path, mode, code):
    with incomplete_catalog(tmp_path, mode) as catalog:
        profile = replace(incomplete_profile(catalog), departure_window_minutes=10)
        result = StaticPlanner(catalog).plan(profile, date(2026, 11, 9))
        assert result.errors[0].code == code and result.data is None


def test_missing_frequency_anchor_still_checks_published_25h_service_date(tmp_path):
    with incomplete_catalog(tmp_path, "frequency_overnight", prior="", after="") as catalog:
        profile = replace(
            incomplete_profile(catalog), kind=ProfileKind.TO_HOME, departure_window_minutes=10
        )
        result = StaticPlanner(catalog).plan(profile, date(2026, 11, 14), time(1))
        assert result.errors[0].code == "SCHEDULE_TIME_UNRESOLVED"
        assert result.warnings[0].code == "SCHEDULE_WINDOW_UNVERIFIED"
        assert result.data is None


@pytest.fixture(scope="module")
def unanchored_frequency_path(tmp_path_factory):
    root = tmp_path_factory.mktemp("unanchored-frequency")
    with incomplete_catalog(root, "frequency", prior="", after=""):
        pass
    return root / "incomplete.sqlite3"


@pytest.mark.parametrize(
    "first,day,departure,code",
    [
        (True, date(2026, 11, 9), time(8, 30), "NO_SCHEDULED_SERVICE"),
        (True, date(2026, 11, 9), time(8, 10), "NO_SCHEDULED_SERVICE"),
        (True, date(2026, 11, 9), time(8), "SCHEDULE_TIME_UNRESOLVED"),
        (True, date(2026, 11, 9), time(7, 50), "SCHEDULE_TIME_UNRESOLVED"),
        (True, date(2026, 11, 9), time(7, 49, 59), "NO_SCHEDULED_SERVICE"),
        (True, date(2026, 11, 9), time(8, 9, 59), "SCHEDULE_TIME_UNRESOLVED"),
        (False, date(2026, 11, 9), time(8, 30), "SCHEDULE_TIME_UNRESOLVED"),
        (True, date(2026, 11, 8), time(8), "NO_SCHEDULED_SERVICE"),
        (True, date(2026, 11, 12), time(8), "NO_SCHEDULED_SERVICE"),
    ],
)
def test_frequency_end_applies_only_to_exact_first_occurrence(
    unanchored_frequency_path, first, day, departure, code
):
    with Catalog(unanchored_frequency_path) as catalog:
        leg = leg_for(catalog, "MAIN", "0006" if first else "0001", "0004", 10 if first else 20, 30)
        profile = replace(
            incomplete_profile(catalog),
            kind=ProfileKind.TO_HOME,
            legs=(leg,),
            departure_window_minutes=10,
        )
        if first:
            assert leg.origin_sequence == 10  # First does not mean sequence=1.
        when = datetime.combine(day, departure, BOGOTA)
        before = catalog.scheduled_connections(leg, when, window_minutes=10)
        result = StaticPlanner(catalog).plan(profile, day, departure)
        assert not result.ok and result.data is None
        assert result.errors[0].code == code
        assert bool(result.warnings) == (code == "SCHEDULE_TIME_UNRESOLVED")
        assert catalog.has_unresolved_boarding(leg, when, when + timedelta(minutes=10)) == (
            code == "SCHEDULE_TIME_UNRESOLVED"
        )
        assert before == catalog.scheduled_connections(leg, when, window_minutes=10) == []
