"""GUI orchestration without Tk widgets; all catalogs/data here are synthetic."""

import json
import shutil
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from test_profiles import WHEN
from test_profiles import profile as previous_profile
from test_profiles import profile_catalogs as previous_catalogs

from transmitracker.gui.config import SECRET_KEYS, LocalConfig
from transmitracker.gui.controller import DesktopController, decode_form, parse_departure
from transmitracker.gui.messages import result_text
from transmitracker.gui.worker import UiWorker
from transmitracker.profiles.contracts import Issue, Result, primitive
from transmitracker.profiles.models import ProfileKind

profile = previous_profile
profile_catalogs = previous_catalogs


@pytest.fixture
def desktop(tmp_path, profile_catalogs):
    (tmp_path / "catalogs").mkdir()
    for index, path in enumerate(profile_catalogs):
        shutil.copy2(path, tmp_path / f"catalogs/v{index}.sqlite3")
    controller = DesktopController(tmp_path)
    preferences = controller.config.read()
    preferences["catalog_path"] = "catalogs/v0.sqlite3"
    controller.config.write(preferences)
    assert controller.bootstrap()["info"]
    return controller


def test_origin_route_pattern_destination_pipeline(desktop, profile):
    stops = desktop.search("anterior")
    assert stops.ok and stops.data[0].stop_id == "0006"
    assert desktop.search("0006").data[0].stop_id == "0006"
    routes = desktop.query("0006", WHEN)
    assert any(v.route_id == "001" and v.short_name == "SYN1" for v in routes.data)
    patterns = desktop.query("0006", WHEN, route_id="001")
    pattern, end = next(
        (p, end) for p, end in patterns.data if p.pattern_id == profile.legs[0].pattern_id
    )
    assert end == "Destino final" and pattern.direction_id == 0
    destinations = desktop.query("0006", WHEN, pattern=pattern)
    assert all(v.sequence > pattern.origin_sequence for v in destinations.data)
    assert destinations.data[-1].stop_id == "0004"
    assert all(v.stop_id != "0006" for v in destinations.data)


def test_unknown_direction_remains_unknown_and_platform_search(desktop):
    stops = desktop.search("A001")
    assert stops.data[0].platform_code == "A" and stops.data[0].parent_station == "STN"
    choices = desktop.query("STN", WHEN, route_id="005")
    assert choices.ok and choices.data and choices.data[0][0].direction_id is None


def test_save_reopen_two_kinds_and_revision_conflict(desktop, profile):
    payload = primitive(profile)
    saved = desktop.save(payload, WHEN, 0)
    assert saved.ok and saved.data.revision == 1
    reopened = DesktopController(desktop.config.root)
    assert reopened.bootstrap()["profiles"].data[0].profile == profile
    assert reopened.config.read()["example_departures"][profile.kind.value] == WHEN.isoformat()
    assert reopened.save(payload, WHEN, 0).errors[0].code == "PROFILE_REVISION_CONFLICT"
    second = replace(profile, profile_id="return", kind=ProfileKind.TO_HOME)
    assert reopened.save(primitive(second), WHEN, 0).ok
    assert len(reopened.bootstrap()["profiles"].data) == 2
    assert reopened.save(payload, WHEN, 1).data.revision == 2


def test_catalog_switch_keeps_profile_pinned(desktop, profile):
    assert desktop.save(primitive(profile), WHEN, 0).ok
    preferences = desktop.config.read()
    preferences["catalog_path"] = "catalogs/v1.sqlite3"
    result = desktop.save_settings(preferences, dict.fromkeys(SECRET_KEYS, ""))
    assert result.ok and result.data == (profile.profile_id,)
    state = desktop.bootstrap()
    saved = state["profiles"].data[0]
    assert saved.profile == profile and saved.revision == 1
    assert saved.active_catalog_sha256 != profile.catalog_sha256
    assert state["profiles"].warnings[0].code == "PROFILE_CATALOG_NOT_ACTIVE"
    assert desktop.validate(primitive(profile), WHEN).ok


def test_unavailable_catalog_is_recoverable(desktop, profile):
    assert desktop.save(primitive(profile), WHEN, 0).ok
    prefs = desktop.config.read()
    prefs["catalog_path"] = "catalogs/missing.sqlite3"
    desktop.config.write(prefs)
    state = desktop.bootstrap()
    assert state["info"] is None and state["catalog_error"]
    assert state["profiles"].data[0].profile == profile
    assert not desktop.config.local("catalogs/missing.sqlite3").exists()
    prefs["catalog_path"] = "catalogs/v0.sqlite3"
    assert desktop.save_settings(prefs, dict.fromkeys(SECRET_KEYS, "")).ok


def test_chained_query_uses_previous_arrival_and_user_transfer(desktop, profile):
    first = replace(profile.legs[0], destination_stop_id="0001", destination_sequence=20)
    second = replace(profile.legs[0], origin_stop_id="0001", origin_sequence=20)
    payload = primitive(replace(profile, legs=(first, second)))
    payload["transfers"] = [{"walking_minutes": "7", "buffer_minutes": "2"}]
    ready = desktop.ready_at(payload, WHEN, 1)
    assert ready.ok and ready.data.isoformat() == "2026-11-09T08:09:00-05:00"
    assert desktop.validate(payload, WHEN).warnings[0].code == "TRANSFER_PATH_UNVERIFIED"


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("initial_walk_minutes", "abc", "INVALID_FORM"),
        ("final_walk_minutes", "-1", "INVALID_MINUTES"),
        ("arrival_deadline", "06:00", "ARRIVAL_DEADLINE_EXCEEDED"),
        ("active_weekdays", [], "INVALID_WEEKDAYS"),
    ],
)
def test_form_errors_use_domain_contracts(desktop, profile, field, value, code):
    payload = primitive(profile)
    payload[field] = value
    result = desktop.validate(payload, WHEN)
    assert not result.ok and result.errors[0].code == code
    assert result_text(result)


def test_secrets_only_in_env_and_preserve_unrelated_lines(desktop):
    env = desktop.config.env_path
    env.write_text("# comentario\nUNRELATED=preserve\n", encoding="utf-8")
    secrets = dict(
        zip(SECRET_KEYS, ('synthetic"key', "synthetic\nTOKEN=bad", "synthetic-chat"), strict=True)
    )
    preferences = desktop.config.read()
    preferences["theme"] = "Claro"
    preferences["notifications_enabled"] = True
    assert desktop.save_settings(preferences, secrets).ok
    assert desktop.config.read_secrets() == secrets
    assert "UNRELATED=preserve" in env.read_text(encoding="utf-8")
    assert desktop.config.read()["theme"] == "Claro"
    assert desktop.config.read()["notifications_enabled"] is True
    combined = desktop.config.path.read_bytes() + desktop.store_path.read_bytes()
    assert b"synthetic" not in combined
    assert "TOKEN=bad" not in env.read_text(encoding="utf-8").splitlines()


def test_settings_paths_and_secret_whitelist(desktop):
    with pytest.raises(ValueError):
        desktop.config.local("../outside.sqlite3")
    prefs = desktop.config.read()
    with pytest.raises(ValueError):
        desktop.config.write({**prefs, "CROMA_API_KEY": "not-a-secret"})
    prefs["collection_interval"] = 40
    assert not desktop.save_settings(prefs, dict.fromkeys(SECRET_KEYS, "")).ok


def test_diagnostics_redact_raw_messages():
    result = Result(errors=(Issue("UNKNOWN_CODE", "catalog", "DO_NOT_RENDER_SECRET"),))
    assert "DO_NOT_RENDER_SECRET" not in result_text(result)
    assert "UNKNOWN_CODE" in result_text(result)


def test_profile_commit_survives_example_preference_write_failure(desktop, profile, monkeypatch):
    def denied(_settings):
        raise OSError("synthetic-write-failure")

    monkeypatch.setattr(desktop.config, "write", denied)
    saved = desktop.save(primitive(profile), WHEN, 0)
    assert saved.ok and saved.data.revision == 1
    assert saved.warnings[-1].code == "EXAMPLE_PREFERENCE_NOT_SAVED"
    assert desktop.load(profile.profile_id).data.profile == profile


def test_settings_io_failure_does_not_activate_new_catalog(desktop, profile, monkeypatch):
    active = desktop.bootstrap()["active_hash"]
    preferences = desktop.config.read()
    preferences["catalog_path"] = "catalogs/v1.sqlite3"

    def denied(_settings):
        raise OSError("synthetic-write-failure")

    monkeypatch.setattr(desktop.config, "write", denied)
    with pytest.raises(OSError):
        desktop.save_settings(preferences, dict.fromkeys(SECRET_KEYS, ""))
    assert desktop.bootstrap()["active_hash"] == active


def test_worker_callbacks_run_on_main_and_suppress_stale_results():
    worker = UiWorker()
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    callbacks = []
    owner = threading.get_ident()

    def first():
        started.set()
        release.wait(3)
        return "stale"

    worker.submit("search", first, lambda v, e: callbacks.append((v, e, threading.get_ident())))
    assert started.wait(3)

    def second():
        finished.set()
        return "current"

    worker.submit("search", second, lambda v, e: callbacks.append((v, e, threading.get_ident())))
    release.set()
    assert finished.wait(3)
    for _ in range(100):
        worker.drain()
        if callbacks:
            break
        time.sleep(0.005)
    worker.close()
    assert callbacks == [("current", None, owner)]


def test_worker_redacts_failures_and_close_discards_callbacks():
    worker = UiWorker()
    done = threading.Event()
    callbacks = []

    def failing():
        done.set()
        raise ValueError("SECRET_VALUE")

    worker.submit("settings", failing, lambda v, e: callbacks.append(e))
    assert done.wait(3)
    for _ in range(100):
        worker.drain()
        if callbacks:
            break
        time.sleep(0.005)
    assert callbacks and "SECRET_VALUE" not in callbacks[0]
    worker.close()
    worker.drain()
    worker.submit("after-close", lambda: 1, lambda v, e: pytest.fail("Closed worker"))


def test_invalid_config_preserved_and_parse_is_local(desktop, profile):
    assert parse_departure("2026-11-09", "07:45") == WHEN
    bad = primitive(profile)
    bad["secret"] = "NOT_ALLOWED"
    assert not decode_form(bad).ok
    desktop.config.path.write_text("{broken", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        LocalConfig(desktop.config.root).read()
    assert desktop.config.path.read_text(encoding="utf-8") == "{broken"
    assert Path(desktop.store_path).exists()
