"""Static planning with synthetic saved profiles; real Tk, isolated by conftest."""

import shutil
import threading
from dataclasses import replace
from datetime import time

import customtkinter as ctk
import pytest
from test_gui_widgets import pump
from test_static_planning import leg_for, work_profile
from test_static_planning import planning_catalog_path as planning_catalog_path

from transmitracker.catalog.queries import Catalog
from transmitracker.gui.app import TransMiTrackerApp
from transmitracker.gui.controller import DesktopController
from transmitracker.profiles.contracts import primitive
from transmitracker.profiles.models import ProfileKind
from transmitracker.profiles.planning import DISCLAIMER


@pytest.fixture
def saved_desktop(tmp_path, planning_catalog_path):
    path = tmp_path / "catalog.sqlite3"
    shutil.copy2(planning_catalog_path, path)
    controller = DesktopController(tmp_path)
    preferences = controller.config.read()
    preferences["catalog_path"] = "catalog.sqlite3"
    controller.config.write(preferences)
    controller.bootstrap()
    with Catalog(path) as catalog:
        profile = work_profile(catalog)
    assert controller.save_configuration(primitive(profile), 0).ok
    returning = replace(profile, profile_id="SYNTHETIC_RETURN", kind=ProfileKind.TO_HOME)
    assert controller.save_configuration(primitive(returning), 0).ok
    return controller, profile, returning


def contents(controller):
    return tuple(
        p.read_bytes()
        for p in (
            controller.store_path,
            controller.config.path,
            controller.config.root / "catalog.sqlite3",
        )
    )


def test_controller_plans_saved_revision_without_any_writes(saved_desktop):
    controller, profile, returning = saved_desktop
    before = contents(controller)
    result = controller.plan_static(profile.profile_id, "2026-11-09", expected_revision=1)
    assert result.ok and result.data.departure_at == "2026-11-09T08:05:00-05:00"
    assert (
        controller.plan_static(returning.profile_id, "2026-11-09").errors[0].code
        == "DEPARTURE_TIME_REQUIRED"
    )
    result = controller.plan_static(returning.profile_id, "2026-11-09", "07:55")
    assert result.ok and result.data.arrival_deadline_at is None
    assert (
        controller.plan_static(profile.profile_id, "bad").errors[0].code == "INVALID_PLANNING_DATE"
    )
    assert (
        controller.plan_static(profile.profile_id, "2026-11-09", expected_revision=2).errors[0].code
        == "PROFILE_REVISION_CONFLICT"
    )
    assert (
        controller.plan_static(profile.profile_id, "2026-11-08").errors[0].code
        == "PROFILE_INACTIVE_DAY"
    )
    assert contents(controller) == before


def test_controller_missing_or_replaced_catalog_does_not_remap(saved_desktop):
    controller, profile, _ = saved_desktop
    path = controller.config.root / "catalog.sqlite3"
    path.rename(path.with_suffix(".saved"))
    assert (
        controller.plan_static(profile.profile_id, "2026-11-09").errors[0].code
        == "CATALOG_UNAVAILABLE"
    )
    assert not path.exists()
    shutil.copy2(path.with_suffix(".saved"), path)
    import sqlite3

    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE catalog_versions SET sha256=?", ("e" * 64,))
    assert (
        controller.plan_static(profile.profile_id, "2026-11-09").errors[0].code
        == "CATALOG_VERSION_MISMATCH"
    )


@pytest.mark.parametrize(
    "clock",
    [
        "7:30",
        "173045",
        "17:30:70",
        "24:00",
        "17:30:45.1",
        "17:30Z",
        "17:30:45-05:00",
        " 17:30",
        "17:30 ",
    ],
)
def test_controller_rejects_clock_formats_without_fallback(saved_desktop, clock):
    controller, _, returning = saved_desktop
    before = contents(controller)
    result = controller.plan_static(returning.profile_id, "2026-11-09", clock)
    assert not result.ok and result.data is None
    assert result.errors[0].code == "INVALID_CLOCK"
    assert contents(controller) == before


@pytest.fixture
def planning_window(saved_desktop):
    controller, profile, returning = saved_desktop
    app = TransMiTrackerApp(controller.config.root)
    failures = []
    app.report_callback_exception = lambda *args: failures.append(args)
    pump(app, lambda: app.snapshot is not None)
    yield app, controller, profile, returning
    app.close()
    assert not failures


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


@pytest.mark.gui
def test_dashboard_action_and_actual_planning_controls(planning_window):
    app, controller, profile, returning = planning_window
    before = contents(controller)
    button = next(
        child
        for child in descendants(app.page)
        if isinstance(child, ctk.CTkButton) and child.cget("text") == "Planificar con GTFS estático"
    )
    button.invoke()
    panel = app.planning_panel
    panel.day_var.set("2026-11-09")
    panel.button.invoke()
    pump(app, lambda: panel.last_result is not None)
    assert panel.last_result.ok
    assert DISCLAIMER in panel.output.cget("text")
    assert "08:05:00" in panel.output.cget("text")
    assert "no observada" in panel.output.cget("text")
    stored = next(
        s for s in app.snapshot["profiles"].data if s.profile.profile_id == returning.profile_id
    )
    app.open_static_planning(stored)
    panel = app.planning_panel
    panel.day_var.set("2026-11-09")
    panel.button.invoke()
    pump(app, lambda: panel.last_result is not None)
    assert panel.last_result.errors[0].code == "DEPARTURE_TIME_REQUIRED"
    panel.clock_var.set("07:55")
    panel.button.invoke()
    pump(app, lambda: panel.last_result is not None)
    assert panel.last_result.ok and panel.last_result.data.arrival_deadline_at is None
    assert contents(controller) == before


@pytest.mark.gui
def test_changed_date_and_closed_page_discard_worker_results(planning_window, monkeypatch):
    app, controller, profile, _ = planning_window
    stored = next(
        s for s in app.snapshot["profiles"].data if s.profile.profile_id == profile.profile_id
    )
    app.open_static_planning(stored)
    panel = app.planning_panel
    panel.day_var.set("2026-11-09")
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    original = app.controller.plan_static
    worker_threads = []

    def delayed(*args, **kwargs):
        worker_threads.append(threading.get_ident())
        entered.set()
        assert release.wait(5)
        try:
            return original(*args, **kwargs)
        finally:
            finished.set()

    monkeypatch.setattr(app.controller, "plan_static", delayed)
    panel.request()
    pump(app, entered.is_set)
    panel.day_var.set("2026-11-12")
    release.set()
    pump(app, finished.is_set)
    app.worker.drain()
    assert panel.last_result is None
    assert "modificada" in panel.output.cget("text")
    panel.request()
    pump(app, lambda: panel.last_result is not None)
    assert panel.last_result.errors[0].code == "NO_SCHEDULED_SERVICE"
    assert all(thread != threading.get_ident() for thread in worker_threads)
    entered.clear()
    release.clear()
    finished.clear()
    panel.request()
    pump(app, entered.is_set)
    app.dashboard()
    release.set()
    pump(app, finished.is_set)
    app.worker.drain()
    assert not panel.winfo_exists()


@pytest.mark.gui
@pytest.mark.parametrize("microseconds", [0, 500000])
def test_saved_seconds_survive_real_panel_controller_service_flow(
    saved_desktop, monkeypatch, microseconds
):
    controller, _, returning = saved_desktop
    with Catalog(controller.config.root / "catalog.sqlite3") as catalog:
        profile = replace(
            returning,
            legs=(leg_for(catalog, "EVENING_LATE", b=20),),
            usual_departure=time(17, 30, 45, microseconds),
            initial_walk_minutes=0,
        )
    assert controller.save_configuration(primitive(profile), 1).ok
    app = TransMiTrackerApp(controller.config.root)
    failures = []
    app.report_callback_exception = lambda *args: failures.append(args)
    try:
        pump(app, lambda: app.snapshot is not None)
        stored = next(
            s for s in app.snapshot["profiles"].data if s.profile.profile_id == profile.profile_id
        )
        before = contents(controller)
        sent_clocks = []
        original_plan = app.controller.plan_static

        def observed_plan(profile_id, day, departure_clock=None, **kwargs):
            sent_clocks.append(departure_clock)
            return original_plan(profile_id, day, departure_clock, **kwargs)

        monkeypatch.setattr(app.controller, "plan_static", observed_plan)
        app.open_static_planning(stored)
        panel = app.planning_panel
        original_text = profile.usual_departure.isoformat()
        assert panel.clock.get() == original_text
        assert not panel.clock_edited
        panel.day_var.set("2026-11-09")
        assert not panel.clock_edited  # Date edits do not edit the saved clock.
        panel.button.invoke()
        pump(app, lambda: panel.last_result is not None)
        plan = panel.last_result.data
        assert panel.last_result.ok
        assert plan.departure_at == f"2026-11-09T{original_text}-05:00"
        assert sent_clocks[-1] is None
        assert stored.revision == 2
        assert plan.steps[0].trip_id == "EVENING_LATE"
        assert plan.steps[0].boarding_at == "2026-11-09T17:31:00-05:00"
        for clock, departure, trip in (
            ("17:30", "17:30:00", "EVENING_EARLY"),
            ("17:30:30", "17:30:30", "EVENING_LATE"),
        ):
            panel.clock_var.set(clock)
            panel.button.invoke()
            pump(app, lambda: panel.last_result is not None)
            assert panel.last_result.ok
            assert panel.last_result.data.departure_at == f"2026-11-09T{departure}-05:00"
            assert panel.last_result.data.steps[0].trip_id == trip
            assert sent_clocks[-1] == clock
            assert panel.clock_edited
        for clock, code in (
            ("17:30:70", "INVALID_CLOCK"),
            ("173045", "INVALID_CLOCK"),
            ("", "DEPARTURE_TIME_REQUIRED"),
        ):
            panel.clock_var.set(clock)
            panel.button.invoke()
            pump(app, lambda: panel.last_result is not None)
            assert panel.last_result.errors[0].code == code
            assert panel.last_result.data is None
            assert sent_clocks[-1] == clock
        if microseconds:
            # Retyping the original fractional text is an explicit edit, even
            # when it equals the prefill. It must not bypass the strict parser.
            panel.clock_var.set(original_text)
            panel.button.invoke()
            pump(app, lambda: panel.last_result is not None)
            assert panel.last_result.errors[0].code == "INVALID_CLOCK"
            assert panel.last_result.data is None
            assert sent_clocks[-1] == original_text
        assert contents(controller) == before
    finally:
        app.close()
    assert not failures
