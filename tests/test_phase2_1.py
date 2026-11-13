"""Structural profiles and draft/version migration regressions, entirely offline."""

import json
import re
import sqlite3
import tomllib
from dataclasses import replace
from datetime import datetime, time
from pathlib import Path

import pytest
from test_gui_controller import desktop as previous_desktop
from test_profiles import WHEN
from test_profiles import profile as previous_profile
from test_profiles import profile_catalogs as previous_catalogs

from transmitracker.profiles.contracts import primitive
from transmitracker.profiles.models import ProfileKind, Transfer
from transmitracker.profiles.store import ProfileStore
from transmitracker.version import app_version

desktop = previous_desktop
profile = previous_profile
profile_catalogs = previous_catalogs


def draft_payload(profile):
    values = primitive(profile)
    values["legs"][0]["destination_stop_id"] = ""
    return {
        "profile": values,
        "legs_ui": [
            {
                "uid": "stable-leg-1",
                "mode": "Origen primero",
                "search_text": "Texto incompleto",
                "route_search": "",
                "origin_label": "Parada anterior",
                "route_label": "SYN1",
                "pattern_label": "Patrón guardado",
                "destination_label": "Seleccione…",
                "pending_origin": "0",
                "origin_choice_label": "Seleccione…",
            }
        ],
        "consultation": {"day": "", "clock": ""},
    }


def test_save_structure_without_date_or_departure(desktop, profile):
    result = desktop.save_configuration(primitive(profile), 0)
    assert result.ok and result.data.configuration_state == "configured"
    reopened = type(desktop)(desktop.config.root)
    assert reopened.load(profile.profile_id).data.profile == profile
    assert not reopened.config.read()["example_departures"]
    absent = desktop.validate(
        primitive(profile), datetime.fromisoformat("2035-01-01T08:00:00-05:00")
    )
    assert not absent.ok
    assert desktop.load(profile.profile_id).data.profile == profile


@pytest.mark.parametrize("deadline", [None, time(7)])
def test_return_has_no_required_deadline_and_no_deadline_error(desktop, profile, deadline):
    changed = replace(
        profile, kind=ProfileKind.TO_HOME, arrival_deadline=deadline, usual_departure=None
    )
    payload = primitive(changed)
    assert desktop.save_configuration(payload, 0).ok
    validated = desktop.validate(payload, WHEN)
    assert validated.ok
    assert validated.data.arrival_with_walk_and_margin
    assert desktop.load(changed.profile_id).data.profile.usual_departure is None


def test_work_requires_deadline_only_temporal_deadline_can_fail(desktop, profile):
    missing = replace(profile, arrival_deadline=None)
    assert not desktop.save_configuration(primitive(missing), 0).ok
    early = replace(profile, arrival_deadline=time(7))
    saved = desktop.save_configuration(primitive(early), 0)
    assert saved.ok
    assert desktop.validate(primitive(early), WHEN).errors[0].code == "ARRIVAL_DEADLINE_EXCEEDED"
    assert desktop.load(profile.profile_id).data.profile == early


@pytest.mark.parametrize(
    "changed",
    [
        {"route_id": "002"},
        {"direction_id": 1},
        {"destination_sequence": 0},
        {"pattern_id": "not-a-pattern"},
        {"destination_stop_id": "0005"},
    ],
)
def test_structural_integrity_not_bypassed(desktop, profile, changed):
    changed_profile = replace(profile, legs=(replace(profile.legs[0], **changed),))
    assert not desktop.save_configuration(primitive(changed_profile), 0).ok
    assert not desktop.load(profile.profile_id).ok


def test_transfer_warning_does_not_block_configuration(desktop, profile):
    first = replace(profile.legs[0], destination_stop_id="0001", destination_sequence=20)
    second = replace(profile.legs[0], origin_stop_id="0001", origin_sequence=20)
    configured = replace(profile, legs=(first, second), transfers=(Transfer(17, 4),))
    saved = desktop.save_configuration(primitive(configured), 0)
    assert saved.ok and saved.warnings[0].code == "TRANSFER_PATH_UNVERIFIED"
    assert saved.data.profile.transfers == (Transfer(17, 4),)


def test_draft_resume_is_separate_and_optimistic(desktop, profile):
    assert desktop.save_configuration(primitive(profile), 0).ok
    data = draft_payload(profile)
    saved = desktop.save_draft(data, 0, 1)
    assert saved.ok and saved.data.revision == 1
    assert desktop.save_draft(data, 0, 1).errors[0].code == "DRAFT_REVISION_CONFLICT"
    state = type(desktop)(desktop.config.root).bootstrap()
    assert state["drafts"][0].payload == data
    assert state["profiles"].data[0].profile == profile
    assert state["drafts"][0].base_profile_revision == 1
    assert desktop.save_configuration(primitive(profile), 1, 1).ok
    assert not desktop.bootstrap()["drafts"]
    # The archived draft retains its revision, so reopening/re-editing cannot use revision zero.
    assert desktop.save_draft(data, 1, 2).ok


def test_unknown_secret_field_rejected_in_drafts(desktop, profile):
    data = draft_payload(profile)
    data["profile"]["CROMA_API_KEY"] = "SYNTHETIC_NOT_A_SECRET"
    assert not desktop.save_draft(data, 0, 0).ok


def test_legacy_database_migration_preserves_payload_history_and_revision(desktop, profile):
    assert desktop.save(primitive(profile), WHEN, 0).ok
    with sqlite3.connect(desktop.store_path) as connection:
        # Recreate the exact pre-2.1 representation/schema, without changing the GTFS file.
        payload = primitive(profile)
        payload.pop("usual_departure")
        encoded = json.dumps(payload)
        connection.execute("UPDATE profiles SET payload_json=?", (encoded,))
        connection.execute("UPDATE profile_revisions SET payload_json=?", (encoded,))
        connection.execute("DROP TABLE profile_drafts")
        connection.execute("DROP TABLE profile_schedule_checks")
        connection.execute("PRAGMA user_version=1")
    with ProfileStore(desktop.store_path) as store:
        loaded = store.load(profile.profile_id)
        assert loaded.ok and loaded.data.profile == profile and loaded.data.revision == 1
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assert (
            store.connection.execute("SELECT payload_json FROM profiles").fetchone()[0] == encoded
        )
        assert (
            store.connection.execute("SELECT payload_json FROM profile_revisions").fetchone()[0]
            == encoded
        )
        assert loaded.data.configuration_state == "schedule_validated"


def test_configuration_schedule_and_migration_states(desktop, profile):
    assert desktop.save_configuration(primitive(profile), 0).ok
    assert desktop.load(profile.profile_id).data.configuration_state == "configured"
    assert desktop.validate_example(primitive(profile), WHEN, 1).ok
    assert desktop.load(profile.profile_id).data.configuration_state == "schedule_validated"
    # A new configuration revision invalidates the saved temporal evidence.
    assert desktop.save_configuration(primitive(profile), 1).ok
    assert desktop.load(profile.profile_id).data.configuration_state == "configured"
    preferences = desktop.config.read()
    preferences["catalog_path"] = "catalogs/v1.sqlite3"
    from transmitracker.gui.config import SECRET_KEYS

    assert desktop.save_settings(preferences, dict.fromkeys(SECRET_KEYS, "")).ok
    loaded = desktop.load(profile.profile_id)
    assert loaded.data.configuration_state == "pending_migration"
    assert loaded.data.profile == profile
    assert (
        desktop.save_configuration(primitive(profile), 1).errors[0].code
        == "PROFILE_REVISION_CONFLICT"
    )


@pytest.mark.parametrize("query", ["001", "SYN1", "Ruta sintetica 1"])
def test_route_first_search_patterns_stops_and_order(desktop, profile, query):
    routes = desktop.search_routes(query)
    assert any(r.route_id == "001" for r in routes.data)
    patterns = desktop.query(None, route_id="001")
    pattern = next(p for p, end in patterns.data if p.pattern_id == profile.legs[0].pattern_id)
    origins = desktop.pattern_origins(pattern.pattern_id)
    assert "0004" not in {s.stop_id for s in origins.data}
    origin = next(s for s in origins.data if s.stop_id == "0001")
    pattern = replace(pattern, origin_platform_id=origin.stop_id, origin_sequence=origin.sequence)
    destinations = desktop.query(origin.stop_id, pattern=pattern)
    assert all(d.sequence > origin.sequence for d in destinations.data)
    assert "0006" not in {d.stop_id for d in destinations.data}


def test_wait_contract_does_not_invent_history(desktop, profile):
    with ProfileStore(desktop.store_path) as store:
        check = store.validate_structure(profile)
    assert check.ok and check.data.expected_wait_minutes is None
    assert check.data.wait_basis == "unavailable_no_historical_estimate"


def test_version_is_semver_and_from_project_metadata():
    root = Path(__file__).resolve().parents[1]
    declared = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    assert re.fullmatch(r"\d+\.\d+\.\d+", declared)
    assert app_version() == declared
