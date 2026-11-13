"""Real Tk regression checks for reported data loss, drafts and both selection modes."""

from copy import deepcopy
from threading import Event

import pytest
from test_gui_controller import desktop as previous_desktop
from test_gui_widgets import pump, put
from test_gui_widgets import window as previous_window
from test_profiles import profile_catalogs as previous_catalogs

from transmitracker.gui.editor import ProfileEditor
from transmitracker.profiles.contracts import failure
from transmitracker.profiles.models import ProfileKind
from transmitracker.version import app_version

pytestmark = pytest.mark.gui
desktop = previous_desktop
profile_catalogs = previous_catalogs
window = previous_window


def open_editor(app, kind=ProfileKind.TO_WORK):
    app.open_profile(kind)
    pump(app, lambda: isinstance(app.page, ProfileEditor))
    return app.page


def select_leg(app, editor, index=0):
    leg = editor.legs[index]
    leg.find("anterior")
    pump(app, lambda: bool(leg.matches.winfo_children()))
    leg.matches.winfo_children()[0].invoke()
    pump(app, lambda: bool(leg.routes))
    leg.choose_route(next(k for k, v in leg.routes.items() if v.route_id == "001"))
    pump(app, lambda: bool(leg.patterns))
    leg.choose_pattern(next(iter(leg.patterns)))
    pump(app, lambda: bool(leg.destinations))
    leg.choose_destination(next(k for k, v in leg.destinations.items() if v.stop_id == "0004"))
    return leg


def test_add_remove_preserve_all_values_labels_and_stable_identity(window):
    app, _ = window
    editor = open_editor(app)
    leg = select_leg(app, editor)
    original = deepcopy(leg.snapshot())
    put(editor.initial, "11")
    editor.add_leg()
    assert editor.legs[0].snapshot() == original
    assert editor.initial.get() == "11"
    second = editor.legs[1]
    put(second.search, "Una búsqueda parcial")
    second.search_changed()
    second_snapshot = deepcopy(second.snapshot())
    editor.add_leg()
    assert editor.legs[0].snapshot() == original
    assert editor.legs[1].snapshot() == second_snapshot
    third = editor.legs[2].token
    editor.remove_leg(1)
    assert editor.legs[0].snapshot() == original
    assert editor.legs[1].token == third
    started, release, delivered = Event(), Event(), []
    key = editor.token + f"-{editor.legs[0].token}-routes"

    def old_query():
        started.set()
        release.wait(3)
        return "obsolete"

    app.worker.submit(key, old_query, lambda value, error: delivered.append(value))
    assert started.wait(3)
    editor.add_leg()
    release.set()
    settled = []
    app.after(150, lambda: settled.append(True))
    pump(app, lambda: bool(settled))
    assert not delivered
    assert editor.legs[0].snapshot() == original
    editor.dirty = False


def test_validation_and_query_errors_do_not_clear_form(window, monkeypatch):
    app, _ = window
    editor = open_editor(app)
    leg = select_leg(app, editor)
    snapshot = deepcopy(leg.snapshot())
    put(editor.deadline, "00:01")
    put(editor.day, "2026-11-09")
    put(editor.clock, "07:45")
    editor.commit(False)
    pump(app, lambda: "ARRIVAL_DEADLINE_EXCEEDED" in editor.status.cget("text"))
    assert leg.snapshot() == snapshot
    monkeypatch.setattr(
        app.controller,
        "query",
        lambda *a, **k: failure("CATALOG_UNAVAILABLE", "catalog", "synthetic"),
    )
    leg.fetch_routes()
    pump(app, lambda: "CATALOG_UNAVAILABLE" in editor.status.cget("text"))
    assert leg.snapshot() == snapshot
    # Optional query date is absent; structural save remains valid despite the early deadline.
    put(editor.day, "")
    put(editor.clock, "")
    editor.commit(True)
    pump(app, lambda: editor.revision == 1)
    assert leg.snapshot() == snapshot
    editor.dirty = False


def test_route_first_mode_switch_and_return_without_deadline(window):
    app, _ = window
    editor = open_editor(app, ProfileKind.TO_HOME)
    leg = editor.legs[0]
    leg.switch_mode("Ruta primero")
    leg.find_routes("SYN1")
    pump(app, lambda: bool(leg.routes))
    leg.choose_route(next(k for k, v in leg.routes.items() if v.route_id == "001"))
    pump(app, lambda: bool(leg.patterns))
    # Pick the pattern with the initial stop, through the filtered origin list.
    chosen = None
    for label, pattern in leg.patterns.items():
        origins = app.controller.pattern_origins(pattern.pattern_id)
        if any(o.stop_id == "0006" for o in origins.data):
            chosen = label
            break
    assert chosen
    leg.choose_pattern(chosen)
    pump(app, lambda: bool(leg.origins))
    leg.select_pattern_origin(next(k for k, v in leg.origins.items() if v.stop_id == "0006"))
    pump(app, lambda: bool(leg.destinations))
    leg.choose_destination(next(k for k, v in leg.destinations.items() if v.stop_id == "0004"))
    values = deepcopy(leg.values())
    leg.switch_mode("Origen primero")
    assert leg.values() == values
    leg.switch_mode("Ruta primero")
    pump(app, lambda: bool(leg.origins))
    assert leg.values() == values
    assert editor.payload()["arrival_deadline"] is None
    assert not editor.day.get() and not editor.clock.get()
    editor.commit(True)
    pump(app, lambda: editor.revision == 1)
    assert editor.app.controller.load(editor.profile_id).data.profile.arrival_deadline is None
    assert app_version() in app.title()
    editor.dirty = False
    app.open_profile(ProfileKind.TO_HOME, reload=True)
    pump(app, lambda: isinstance(app.page, ProfileEditor) and app.page is not editor)
    assert app.page.legs[0].mode == "Ruta primero"
    assert app.page.legs[0].values() == values
    assert app.page.legs[0].token == leg.token


def test_draft_reopen_and_unconfirmed_text_cannot_save_as_configured(window):
    app, _ = window
    editor = open_editor(app)
    leg = select_leg(app, editor)
    put(leg.search, "Texto pendiente")
    leg.search_changed()
    put(editor.deadline, "")
    editor.commit(True)
    assert editor.revision == 0
    before = editor.draft_payload()
    editor.save_draft()
    pump(app, lambda: editor.draft_revision == 1)
    assert "Borrador guardado" in editor.status.cget("text")
    editor.dirty = False
    root = app.controller.config.root
    app.close()
    from transmitracker.gui.app import TransMiTrackerApp

    reopened = TransMiTrackerApp(root)
    failures = []
    reopened.report_callback_exception = lambda *args: failures.append(args)
    try:
        pump(reopened, lambda: reopened.snapshot is not None)
        restored = open_editor(reopened)
        assert restored.draft_payload() == before
        assert restored.legs[0].pending_origin
        assert restored.revision == 0 and restored.draft_revision == 1
        restored.dirty = False
    finally:
        reopened.close()
    assert not failures
