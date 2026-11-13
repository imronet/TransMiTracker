"""Actual Tk windows, separate from controller/services; no real HTTP allowed."""

import time

import customtkinter as ctk
import pytest
from test_gui_controller import desktop as desktop_fixture
from test_profiles import profile_catalogs as previous_catalogs

from transmitracker.gui.app import TransMiTrackerApp
from transmitracker.gui.editor import ProfileEditor
from transmitracker.profiles.models import ProfileKind

pytestmark = pytest.mark.gui
desktop = desktop_fixture
profile_catalogs = previous_catalogs


def pump(app, condition, seconds=10):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        app.update()
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError("GUI operation did not finish within the controlled timeout")


def put(widget, value):
    widget.delete(0, "end")
    widget.insert(0, str(value))


@pytest.fixture
def window(desktop):
    app = TransMiTrackerApp(desktop.config.root)
    failures = []
    app.report_callback_exception = lambda *args: failures.append(args)
    pump(app, lambda: app.snapshot is not None)
    yield app, failures
    if not app.closed:
        if isinstance(app.page, ProfileEditor):
            app.page.dirty = False
        app.close()
    assert not failures


def test_window_opens_and_closes_without_network(window):
    app, _ = window
    assert app.winfo_exists() and app.title().startswith("TransMiTracker")
    assert app.snapshot["info"]
    app.diagnostics()
    app.update()
    app.geometry("900x650")
    app.update()
    assert app.content.winfo_width() > 0
    app.settings_page()
    app.update()

    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)

    assert (
        len(
            [
                w
                for w in descendants(app.page)
                if isinstance(w, ctk.CTkEntry) and w.cget("show") == "•"
            ]
        )
        == 3
    )
    try:
        ctk.set_appearance_mode("light")
        ctk.set_widget_scaling(1.25)
        ctk.set_window_scaling(1.25)
        app.update()
        assert ctk.get_appearance_mode() == "Light"
        assert app.content.winfo_width() > 0
    finally:
        ctk.set_widget_scaling(1)
        ctk.set_window_scaling(1)
        ctk.set_appearance_mode("dark")
    app.dashboard()
    app.update()
    app.close()
    assert app.closed


def test_widget_pipeline_save_close_reopen(window):
    app, _ = window
    app.open_profile(ProfileKind.TO_WORK)
    pump(app, lambda: isinstance(app.page, ProfileEditor))
    editor = app.page
    put(editor.day, "2026-11-09")
    put(editor.clock, "07:45")
    put(editor.deadline, "10:00")
    leg = editor.legs[0]
    leg.find("anterior")
    pump(app, lambda: bool(leg.matches.winfo_children()))
    button = leg.matches.winfo_children()[0]
    assert isinstance(button, ctk.CTkButton)
    button.invoke()
    pump(app, lambda: bool(leg.routes))
    assert leg.matches.winfo_height() < 10
    label = next(k for k, v in leg.routes.items() if v.route_id == "001")
    leg.choose_route(label)
    pump(app, lambda: bool(leg.patterns))
    leg.choose_pattern(next(iter(leg.patterns)))
    pump(app, lambda: bool(leg.destinations))
    label = next(k for k, v in leg.destinations.items() if v.stop_id == "0004")
    leg.choose_destination(label)
    editor.commit(True)
    pump(app, lambda: editor.revision == 1)
    assert "guardado" in editor.status.cget("text")
    app.close()
    reopened = TransMiTrackerApp(app.controller.config.root)
    failures = []
    reopened.report_callback_exception = lambda *args: failures.append(args)
    try:
        pump(reopened, lambda: reopened.snapshot is not None)
        reopened.open_profile(ProfileKind.TO_WORK)
        pump(reopened, lambda: isinstance(reopened.page, ProfileEditor))
        assert reopened.page.revision == 1
        assert reopened.page.legs[0].values()["destination_stop_id"] == "0004"
        assert reopened.page.day.get() == "2026-11-09"
        assert reopened.page.deadline.get() == "10:00:00"
    finally:
        if isinstance(reopened.page, ProfileEditor):
            reopened.page.dirty = False
        reopened.close()
    assert not failures


def test_widget_upstream_changes_preserve_independent_structural_choices(window):
    app, _ = window
    app.open_profile(ProfileKind.TO_HOME)
    pump(app, lambda: isinstance(app.page, ProfileEditor))
    editor = app.page
    for _ in range(3):
        editor.add_leg()
    assert len(editor.legs) == 3 and len(editor.transfer_entries) == 2
    editor.legs[1].route = "SYNTHETIC"
    editor.changed(0)
    assert editor.legs[1].route == "SYNTHETIC"
    editor.remove_leg(1)
    assert len(editor.legs) == 2 and len(editor.transfer_entries) == 1
    editor.temporal_changed()
    assert all(v.pattern is None for v in editor.legs)
    editor.dirty = False


def test_missing_catalog_window_remains_navigable(desktop):
    prefs = desktop.config.read()
    prefs["catalog_path"] = "missing.sqlite3"
    desktop.config.write(prefs)
    app = TransMiTrackerApp(desktop.config.root)
    failures = []
    app.report_callback_exception = lambda *args: failures.append(args)
    try:
        pump(app, lambda: app.snapshot is not None)
        assert app.snapshot["info"] is None
        app.open_profile(ProfileKind.TO_WORK)
        pump(app, lambda: isinstance(app.page, ProfileEditor))
        app.settings_page()
        app.update()
        assert app.page
    finally:
        app.close()
    assert not failures
