"""Profile adaptation only; synthetic stores/reports and the unchanged OD engine."""

import hashlib
import json
import shutil
import sqlite3
from dataclasses import replace
from datetime import datetime, time

import pytest
from test_od_analyzer import pattern, report

from transmitracker.catalog.queries import Catalog
from transmitracker.profiles.contracts import primitive
from transmitracker.profiles.models import Leg, Profile, ProfileKind, Transfer
from transmitracker.profiles.reader import ProfileReadError, ReadOnlyProfileStore
from transmitracker.profiles.store import ProfileStore
from transmitracker.reconstruction.models import canonical
from transmitracker.reconstruction.scenarios import create_catalog
from transmitracker.research import od_analyzer as od
from transmitracker.research import profile_od as adapter


@pytest.fixture(scope="module")
def catalog_path(tmp_path_factory):
    return create_catalog(tmp_path_factory.mktemp("profile-od-synthetic"))


def configured_profiles(catalog):
    sha, p = catalog.info()["sha256"], pattern(catalog)
    a = Leg("DEMO_LINE_A", "DEMO_LINE", p, 0, 10, "DEMO_LINE_B", 20)
    b = replace(
        a,
        origin_stop_id="DEMO_LINE_B",
        origin_sequence=20,
        destination_stop_id="DEMO_LINE_C",
        destination_sequence=30,
    )
    c = replace(
        b,
        origin_stop_id="DEMO_LINE_C",
        origin_sequence=30,
        destination_stop_id="DEMO_LINE_Z",
        destination_sequence=40,
    )
    work = Profile(
        "SYNTH_PRIVATE_WORK",
        ProfileKind.TO_WORK,
        sha,
        (a,),
        (),
        1,
        2,
        time(10),
        time(7),
        (0, 1, 2, 3, 4),
    )
    home = replace(
        work,
        profile_id="SYNTH_PRIVATE_HOME",
        kind=ProfileKind.TO_HOME,
        legs=(a, b, c),
        transfers=(Transfer(1), Transfer(2)),
        arrival_deadline=None,
    )
    return work, home


@pytest.fixture
def inputs(tmp_path, catalog_path):
    db, gps = tmp_path / "profiles.sqlite3", tmp_path / "report.json"
    with Catalog(catalog_path) as catalog:
        profiles = configured_profiles(catalog)
        gps.write_text(json.dumps(report(catalog)), encoding="utf-8")
    with ProfileStore(db) as store:
        assert store.register_catalog(catalog_path).ok
        assert store.activate_catalog(
            profiles[0].catalog_sha256,
            changed_at=datetime.fromisoformat("2026-11-14T08:00:00-05:00"),
        ).ok
        for profile in profiles:
            assert store.save_configuration(profile).ok
    return db, gps, catalog_path, profiles


def test_one_leg_work_profile_exactly_matches_direct_od(inputs):
    db, gps, catalog_path, profiles = inputs
    adapted = adapter.run(db, gps, catalog_path, kind="home_to_work", leg_index=1)
    leg = profiles[0].legs[0]
    with Catalog(catalog_path) as catalog:
        expected = od.analyze(
            json.loads(gps.read_text()),
            catalog,
            leg.route_id,
            leg.pattern_id,
            leg.origin_stop_id,
            leg.destination_stop_id,
            origin_sequence=leg.origin_sequence,
            destination_sequence=leg.destination_sequence,
            report_hash=hashlib.sha256(gps.read_bytes()).hexdigest(),
        )
    assert adapted["analysis"] == expected
    assert adapted["leg"] == primitive(leg) and adapted["profile"]["revision"] == 1
    assert adapted["analysis"]["summary"]["duration_candidates"] == 1
    assert adapted["profile_store_read_only"] and not adapted["operationally_validated"]


def test_three_leg_return_profile_selects_only_intermediate_leg(inputs):
    db, gps, catalog_path, profiles = inputs
    with Catalog(catalog_path) as catalog:
        payload = report(catalog, (300, 500, 600, 900, 1000), (0, 20, 30, 60, 70))
    gps.write_text(json.dumps(payload), encoding="utf-8")
    result = adapter.run(db, gps, catalog_path, profile_id=profiles[1].profile_id, leg_index=2)
    assert result["leg"] == primitive(profiles[1].legs[1]) == result["analysis"]["leg"]
    assert result["profile"]["kind"] == "work_to_home" and result["leg_index"] == 2
    assert result["analysis"]["summary"]["duration_candidates"] == 1
    assert result["analysis"]["leg"]["origin_sequence"] == 20
    assert result["analysis"]["leg"]["destination_sequence"] == 30


@pytest.mark.parametrize("index", [0, -1, 4, True, 1.5])
def test_invalid_leg_index_rejected(inputs, index):
    db, gps, catalog, _ = inputs
    with pytest.raises(adapter.ProfileODInputError, match="LEG_INDEX"):
        adapter.run(db, gps, catalog, kind="work_to_home", leg_index=index)


def test_missing_profile_and_no_implicit_profile(inputs):
    db, gps, catalog, _ = inputs
    with pytest.raises(adapter.ProfileODInputError, match="PROFILE_NOT_FOUND"):
        adapter.run(db, gps, catalog, profile_id="ABSENT", leg_index=1)
    with pytest.raises(adapter.ProfileODInputError, match="SELECTION_REQUIRED"):
        adapter.run(db, gps, catalog, leg_index=1)


def test_draft_only_is_not_a_configured_profile(tmp_path, catalog_path):
    db = tmp_path / "draft-only.sqlite3"
    with ProfileStore(db) as store:
        store.connection.execute(
            "INSERT INTO profile_drafts VALUES (?,?,?,?,?,?,0)",
            ("DRAFT", "home_to_work", "{}", 1, 0, "2026-11-14T08:00:00-05:00"),
        )
        store.connection.commit()
    before = db.read_bytes()
    assert adapter.list_configured(db) == []
    with ReadOnlyProfileStore(db) as store:
        assert store.select(kind="home_to_work").errors[0].code == "PROFILE_NOT_FOUND"
    assert before == db.read_bytes()


@pytest.mark.parametrize("metadata", [None, {"sha256": "f" * 64}])
def test_report_catalog_must_match_profile_and_local_catalog(inputs, metadata):
    db, gps, catalog, _ = inputs
    payload = json.loads(gps.read_text())
    payload["catalog"] = metadata
    gps.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(adapter.ProfileODInputError, match="REPORT_CATALOG"):
        adapter.run(db, gps, catalog, kind="home_to_work", leg_index=1)


def test_pending_migration_retained_old_catalog_allowed_new_one_rejected(inputs, tmp_path):
    db, gps, catalog, _ = inputs
    newer = tmp_path / "newer.sqlite3"
    shutil.copyfile(catalog, newer)
    with sqlite3.connect(newer) as connection:
        connection.execute("UPDATE catalog_versions SET sha256=?", ("f" * 64,))
    with ProfileStore(db) as store:
        assert store.register_catalog(newer).ok
        assert store.activate_catalog(
            "f" * 64, changed_at=datetime.fromisoformat("2026-11-14T09:00:00-05:00")
        ).ok
    before = db.read_bytes()
    with pytest.raises(adapter.ProfileODInputError, match="PROFILE_CATALOG"):
        adapter.run(db, gps, newer, kind="home_to_work", leg_index=1)
    result = adapter.run(db, gps, catalog, kind="home_to_work", leg_index=1)
    assert result["profile"]["configuration_state"] == "pending_migration"
    assert "PROFILE_CATALOG_NOT_ACTIVE" in result["profile_warning_codes"]
    assert result["profile"]["active_catalog_sha256"] == "f" * 64
    assert before == db.read_bytes()


def test_reader_never_initializes_schema_or_writes_database(inputs, monkeypatch):
    db, gps, catalog, _ = inputs
    before = db.read_bytes()
    directory = sorted(p.name for p in db.parent.iterdir())
    with sqlite3.connect(db) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        schema = connection.execute("SELECT sql FROM sqlite_master ORDER BY name").fetchall()
    monkeypatch.setattr(
        ProfileStore, "__init__", lambda *args: pytest.fail("Writer constructor invoked")
    )
    for _ in range(2):
        assert len(adapter.list_configured(db)) == 2
        adapter.run(db, gps, catalog, kind="home_to_work", leg_index=1)
    with ReadOnlyProfileStore(db) as store:
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == version
        assert [
            tuple(row)
            for row in store.connection.execute("SELECT sql FROM sqlite_master ORDER BY name")
        ] == schema
        with pytest.raises(sqlite3.OperationalError):
            store.connection.execute("UPDATE profiles SET revision=99")
        with pytest.raises(sqlite3.OperationalError):
            store.connection.execute("PRAGMA user_version=99")
    assert db.read_bytes() == before
    assert sorted(p.name for p in db.parent.iterdir()) == directory


@pytest.mark.parametrize("mode", ["missing", "old_schema", "unrelated"])
def test_missing_or_incompatible_store_never_created_or_migrated(tmp_path, mode):
    db = tmp_path / "invalid.sqlite3"
    if mode != "missing":
        with sqlite3.connect(db) as connection:
            connection.execute("PRAGMA user_version=" + ("1" if mode == "old_schema" else "2"))
            connection.execute("CREATE TABLE unrelated (value)")
    before = db.read_bytes() if db.exists() else None
    with pytest.raises(ProfileReadError):
        adapter.list_configured(db)
    assert db.read_bytes() == before if before is not None else not db.exists()


def test_direction_and_parent_platform_mismatch_are_not_silently_resolved(inputs, tmp_path):
    db, gps, catalog, profiles = inputs
    with sqlite3.connect(db) as connection:
        payload = primitive(profiles[0])
        payload["legs"][0]["direction_id"] = 1
        connection.execute(
            "UPDATE profiles SET payload_json=? WHERE profile_id=?",
            (json.dumps(payload), profiles[0].profile_id),
        )
    with pytest.raises(adapter.ProfileODInputError, match="EXACT_LEG_MISMATCH"):
        adapter.run(db, gps, catalog, kind="home_to_work", leg_index=1)
    parent_catalog = tmp_path / "parent.sqlite3"
    shutil.copyfile(catalog, parent_catalog)
    with sqlite3.connect(parent_catalog) as connection:
        connection.execute(
            "INSERT INTO stops(stop_id,name,location_type) VALUES ('SYNTH_PARENT','Synthetic parent',1)"
        )
        connection.execute(
            "UPDATE stops SET parent_station='SYNTH_PARENT' WHERE stop_id='DEMO_LINE_A'"
        )
    parent = replace(
        profiles[0], legs=(replace(profiles[0].legs[0], origin_stop_id="SYNTH_PARENT"),)
    )
    with Catalog(parent_catalog) as local:
        local.validate_leg_structure(parent.legs[0])  # Profile contract permits this family.
    with sqlite3.connect(db) as connection:
        connection.execute(
            "UPDATE profiles SET payload_json=? WHERE profile_id=?",
            (json.dumps(primitive(parent)), parent.profile_id),
        )
    with pytest.raises(adapter.ProfileODInputError, match="EXACT_LEG_MISMATCH"):
        adapter.run(db, gps, parent_catalog, kind="home_to_work", leg_index=1)


@pytest.mark.parametrize("case", ["missing_destination", "recross"])
def test_od_indeterminacy_and_recross_rejection_propagate_unchanged(inputs, case):
    db, gps, catalog_path, _ = inputs
    positions, times = (
        ((0, 100, 200), (0, 20, 40))
        if case == "missing_destination"
        else (
            (100, 150, 141, 132, 123, 114, 105, 150, 400, 475),
            (0, 10, 11, 12, 13, 14, 15, 25, 35, 45),
        )
    )
    with Catalog(catalog_path) as catalog:
        gps.write_text(json.dumps(report(catalog, positions, times)), encoding="utf-8")
    result = adapter.run(db, gps, catalog_path, kind="home_to_work", leg_index=1)
    assert result["analysis"]["summary"]["duration_candidates"] == 0
    if case == "recross":
        assert "origin_recross_or_cumulative_reversal" in result["analysis"]["summary"]["reasons"]


def test_cli_listing_selection_privacy_protected_output_and_reproducibility(
    inputs, tmp_path, monkeypatch, capsys
):
    db, gps, catalog, _ = inputs
    monkeypatch.setattr("transmitracker.research.local_pilot.PILOT_ROOT", tmp_path)
    assert adapter.main(["list", "--profiles", str(db)]) == 0
    listing = capsys.readouterr().out
    assert "home_to_work" in listing and "work_to_home" in listing
    assert "SYNTH_PRIVATE" not in listing and "DEMO_LINE" not in listing
    assert adapter.list_configured(db, kind="work_to_home")[0]["leg_indices"] == [1, 2, 3]
    args = [
        "analyze",
        "--profiles",
        str(db),
        "--profile-kind",
        "home_to_work",
        "--leg",
        "1",
        "--report",
        str(gps),
        "--catalog",
        str(catalog),
    ]
    outputs = (tmp_path / "one.json", tmp_path / "two.json")
    for output in outputs:
        assert adapter.main([*args, "--output", str(output)]) == 0
    a, b = [json.loads(p.read_text(encoding="utf-8")) for p in outputs]
    assert canonical(a["analysis"]) == canonical(b["analysis"])
    console = capsys.readouterr().out
    assert all(secret not in console for secret in ("SYNTH_PRIVATE", "DEMO_LINE", "DEMO_VEHICLE"))
    for output in (outputs[0], db, tmp_path.parent / "escape.json"):
        with pytest.raises(SystemExit) as stopped:
            adapter.main([*args, "--output", str(output)])
        assert stopped.value.code == 2
    for removed in (("--leg", "1"), ("--profile-kind", "home_to_work")):
        incomplete = [v for v in args if v not in removed]
        with pytest.raises(SystemExit):
            adapter.main([*incomplete, "--output", str(tmp_path / "never.json")])
