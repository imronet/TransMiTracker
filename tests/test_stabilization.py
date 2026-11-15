"""v0.7.1: complete discarded evidence and real desktop presentation, offline."""

import threading
from dataclasses import replace
from datetime import date, datetime, time, timedelta

import customtkinter as ctk
import pytest
from test_gui_widgets import pump
from test_planning_gui import contents, descendants
from test_planning_gui import planning_window as planning_window
from test_planning_gui import saved_desktop as saved_desktop
from test_static_planning import leg_for, work_profile
from test_static_planning import planning_catalog_path as planning_catalog_path

from transmitracker.catalog.queries import Catalog
from transmitracker.gui.app import TransMiTrackerApp
from transmitracker.gui.editor import ProfileEditor
from transmitracker.gui.messages import field_label, result_text, technical_text, window_help
from transmitracker.gui.planning import diagnostic_text
from transmitracker.profiles.contracts import Issue, Result, primitive
from transmitracker.profiles.models import ProfileKind, Transfer
from transmitracker.profiles.planning import StaticPlanner
from transmitracker.version import app_version


def late_profile(catalog, count):
    profile = work_profile(catalog)
    if count == 1:
        return replace(profile, arrival_deadline=time(8, 24))
    first = leg_for(catalog, destination="0001", b=20)
    second = leg_for(
        catalog, "L2", "0001", "0004" if count == 2 else "0003", 10, 30 if count == 2 else 20
    )
    legs = (
        (first, second)
        if count == 2
        else (first, second, leg_for(catalog, "L3", "0003", "0004", 10, 20))
    )
    return replace(
        profile,
        legs=legs,
        transfers=(Transfer(2, 3),) * (count - 1),
        arrival_deadline=time(8, 39) if count == 2 else time(8, 49),
    )


@pytest.mark.parametrize("count", [1, 2, 3])
def test_late_complete_chain_is_evidence_never_a_recommendation(planning_catalog_path, count):
    with Catalog(planning_catalog_path) as catalog:
        planner = StaticPlanner(catalog)
        profile = late_profile(catalog, count)
        result = planner.consult(profile, date(2026, 11, 9))
        assert not result.ok and result.data is None
        assert result.errors[0].code == "ARRIVAL_DEADLINE_EXCEEDED"
        diagnostic = result.diagnostic
        assert diagnostic.status == "discarded_not_recommendation"
        assert diagnostic.lateness_seconds == 60
        plan = diagnostic.discarded
        assert len(plan.steps) == count
        assert diagnostic.search_start == plan.search_start
        assert diagnostic.boarding_horizon_end == plan.boarding_horizon_end
        assert (
            plan.initial_walk_minutes == 5
            and plan.final_walk_minutes == 2
            and plan.safety_margin_minutes == 3
        )
        for index, step in enumerate(plan.steps):
            assert datetime.fromisoformat(step.ready_at) <= datetime.fromisoformat(step.boarding_at)
            assert step.boarding_at <= plan.boarding_horizon_end
            trip = catalog.connection.execute(
                "SELECT * FROM trips WHERE trip_id=?", (step.trip_id,)
            ).fetchone()
            assert trip["service_id"] in catalog.active_services(
                date.fromisoformat(step.service_date)
            )
            assert trip["pattern_id"] == profile.legs[index].pattern_id
            if index:
                ready = datetime.fromisoformat(plan.steps[index - 1].arrival_at) + timedelta(
                    minutes=5
                )
                assert ready.isoformat() == step.ready_at
        assert result.to_dict() == planner.consult(profile, date(2026, 11, 9)).to_dict()


def test_isolated_late_final_leg_is_not_a_personal_itinerary(planning_catalog_path):
    with Catalog(planning_catalog_path) as catalog:
        profile = replace(late_profile(catalog, 2), transfers=(Transfer(100, 0),))
        result = StaticPlanner(catalog).consult(profile, date(2026, 11, 9))
        assert result.errors[0].code == "ARRIVAL_DEADLINE_EXCEEDED"
        assert result.diagnostic.discarded is None and result.diagnostic.lateness_seconds is None
        assert result.data is None


def test_exact_deadline_and_context_do_not_relax_acceptance(planning_catalog_path):
    with Catalog(planning_catalog_path) as catalog:
        planner = StaticPlanner(catalog)
        profile = work_profile(catalog)
        direct = planner.plan(profile, date(2026, 11, 9))
        result = planner.consult(profile, date(2026, 11, 9))
        assert direct.ok and result.ok and direct.data == result.data
        assert result.data.arrival_with_margin_at == result.data.arrival_deadline_at
        assert result.diagnostic is None
        inactive = planner.consult(profile, date(2026, 11, 8))
        assert inactive.errors[0].code == "PROFILE_INACTIVE_DAY"
        assert inactive.diagnostic.discarded is None


def test_opening_current_store_and_reading_dashboard_is_byte_stable(saved_desktop):
    controller, profile, _ = saved_desktop
    before = contents(controller)
    for _ in range(2):
        assert controller.bootstrap()["profiles"].ok
        assert controller.load(profile.profile_id).ok
        assert controller.describe(profile)
    assert contents(controller) == before


def test_initial_walk_outside_window_has_a_specific_explanation(planning_catalog_path, monkeypatch):
    with Catalog(planning_catalog_path) as catalog:

        def unexpected_query(*args, **kwargs):
            pytest.fail("Boarding search must not start")

        monkeypatch.setattr(catalog, "scheduled_connections", unexpected_query)
        profile = replace(
            work_profile(catalog),
            kind=ProfileKind.TO_HOME,
            initial_walk_minutes=10,
            departure_window_minutes=1,
        )
        result = StaticPlanner(catalog).consult(profile, date(2026, 11, 9), time(8))
        assert result.errors[0].code == "HORIZON_INSUFFICIENT"
        assert result.data is None and result.diagnostic.discarded is None
        assert "caminata inicial termina después" in diagnostic_text(result.diagnostic)
        assert "No se buscaron abordajes" in diagnostic_text(result.diagnostic)
        assert "Ventana configurada" in diagnostic_text(result.diagnostic)
        assert "realmente examinada" not in diagnostic_text(result.diagnostic)


def test_inactive_profile_shows_configured_window_without_claiming_a_search(
    planning_catalog_path, monkeypatch
):
    with Catalog(planning_catalog_path) as catalog:

        def unexpected_query(*args, **kwargs):
            pytest.fail("Boarding search must not start for an inactive profile")

        monkeypatch.setattr(catalog, "scheduled_connections", unexpected_query)
        result = StaticPlanner(catalog).consult(work_profile(catalog), date(2026, 11, 8))
        assert result.errors[0].code == "PROFILE_INACTIVE_DAY"
        text = diagnostic_text(result.diagnostic)
        assert "Ventana configurada" in text and "No se buscaron abordajes" in text
        assert "perfil no está activo" in text and "realmente examinada" not in text


@pytest.mark.gui
@pytest.mark.parametrize("field", ["date", "clock"])
def test_positive_edit_query_and_worker_error_reset_heading(planning_window, monkeypatch, field):
    app, controller, _, returning = planning_window
    stored = next(
        s for s in app.snapshot["profiles"].data if s.profile.profile_id == returning.profile_id
    )
    app.open_static_planning(stored)
    panel = app.planning_panel
    panel.day_var.set("2026-11-09")
    panel.clock_var.set("07:55")
    before = contents(controller)
    panel.request()
    pump(app, lambda: panel.last_result is not None)
    assert panel.last_result.ok
    positive_color = panel.result_title.cget("text_color")
    assert panel.result_title.cget("text") == "Itinerario programado encontrado"
    if field == "date":
        panel.day_var.set("2026-11-10")
    else:
        panel.clock_var.set("07:56")
    assert panel.result_title.cget("text") == "Consulta pendiente"
    assert panel.result_title.cget("text_color") != positive_color
    assert panel.last_result is None and not panel.detail_area.winfo_children()
    entered, release = threading.Event(), threading.Event()
    original = app.controller.plan_static

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(app.controller, "plan_static", delayed)
    try:
        panel.request()
        pump(app, entered.is_set)
        assert panel.result_title.cget("text") == "Consultando horarios publicados"
        assert panel.result_title.cget("text_color") != positive_color
    finally:
        release.set()
    pump(app, lambda: panel.last_result is not None)
    assert panel.last_result.ok

    def broken(*args, **kwargs):
        raise RuntimeError("PRIVATE_WORKER_ERROR")

    monkeypatch.setattr(app.controller, "plan_static", broken)
    panel.request()  # No edit: a new request must also clear the successful heading.
    assert panel.result_title.cget("text") == "Consultando horarios publicados"
    pump(app, lambda: panel.result_title.cget("text") == "Error en la consulta")
    assert panel.result_title.cget("text_color") != positive_color
    assert panel.last_result is None and not panel.detail_area.winfo_children()
    assert "PRIVATE_WORKER_ERROR" not in panel.output.cget("text")
    assert contents(controller) == before


@pytest.mark.parametrize(
    "code",
    [
        "ARRIVAL_DEADLINE_EXCEEDED",
        "NO_SCHEDULED_SERVICE",
        "SCHEDULE_TIME_UNRESOLVED",
        "HORIZON_INSUFFICIENT",
        "TRANSFER_INCOMPATIBLE",
        "PROFILE_INACTIVE_DAY",
        "CATALOG_UNAVAILABLE",
        "CATALOG_VERSION_MISMATCH",
        "DEPARTURE_TIME_REQUIRED",
    ],
)
def test_user_messages_are_distinct_and_technical_details_opt_in(code):
    result = Result(errors=(Issue(code, "departure_window_minutes", "PRIVATE_MESSAGE"),))
    text = result_text(result)
    assert (
        code not in text
        and "departure_window_minutes" not in text
        and "PRIVATE_MESSAGE" not in text
    )
    assert "Ventana de búsqueda" in text
    assert code in technical_text(result)


@pytest.mark.parametrize("negative", [False, True])
@pytest.mark.gui
def test_hierarchical_results_and_accessible_technical_details(saved_desktop, negative):
    controller, profile, _ = saved_desktop
    with Catalog(controller.config.root / "catalog.sqlite3") as catalog:
        configured = late_profile(catalog, 2)
        if not negative:
            configured = replace(configured, arrival_deadline=time(8, 50))
    assert controller.save_configuration(primitive(configured), 1).ok
    app = TransMiTrackerApp(controller.config.root)
    errors = []
    app.report_callback_exception = lambda *args: errors.append(args)
    try:
        pump(app, lambda: app.snapshot is not None)
        texts = [w.cget("text") for w in descendants(app.sidebar) if isinstance(w, ctk.CTkLabel)]
        assert not any("Fase 2.1" in text for text in texts)
        assert any(app_version() in text for text in texts) and app_version() in app.title()
        stored = next(
            s for s in app.snapshot["profiles"].data if s.profile.profile_id == profile.profile_id
        )
        before = contents(controller)
        app.open_static_planning(stored)
        panel = app.planning_panel
        panel.day_var.set("2026-11-09")
        panel.request()
        pump(app, lambda: panel.last_result is not None)
        assert panel.last_result.ok == (not negative)
        assert len(panel.detail_area.winfo_children()) >= 3
        app.update()
        assert not panel.technical.winfo_ismapped()
        main = "\n".join(
            w.cget("text")
            for w in descendants(panel)
            if isinstance(w, ctk.CTkLabel) and w is not panel.technical
        )
        for raw in (
            "transfers.0",
            "TRANSFER_PATH_UNVERIFIED",
            "ARRIVAL_DEADLINE_EXCEEDED",
            "departure_window_minutes",
        ):
            assert raw not in main
        assert "caminata" in main.lower() and "tolerancia" in main.lower()
        if negative:
            assert "Alternativa programada descartada" in main
            assert "Supera el límite en 1 min" in main
            assert panel.last_result.data is None
        else:
            assert "Itinerario programado encontrado" in panel.result_title.cget("text")
            assert "Primer transbordo" in main
        panel.toggle_technical()
        app.update()
        assert panel.technical.winfo_ismapped()
        assert technical_text(panel.last_result) in panel.technical.cget("text")
        assert contents(controller) == before
    finally:
        app.close()
    assert not errors


@pytest.mark.gui
def test_themes_editor_navigation_and_window_help(saved_desktop):
    controller, profile, _ = saved_desktop
    app = TransMiTrackerApp(controller.config.root)
    errors = []
    app.report_callback_exception = lambda *args: errors.append(args)
    try:
        pump(app, lambda: app.snapshot is not None)
        before = contents(controller)
        for theme in ("light", "dark"):
            ctk.set_appearance_mode(theme)
            app.geometry("900x650")
            for kind in ProfileKind:
                app.open_profile(kind)
                pump(app, lambda: isinstance(app.page, ProfileEditor))
                editor = app.page
                assert editor.revision == 1 and not editor.dirty
                assert editor.window.get() == "120"
                assert "No es espera" in window_help(kind)
                app.dashboard()
                app.update()
        assert contents(controller) == before
        assert "Primer transbordo" in field_label("transfers.0")
    finally:
        app.close()
    assert not errors
