"""SQLite, saved-Protobuf adapters and CLI integration, with no network access."""

import hashlib
import json
from dataclasses import replace

import pytest
from google.transit import gtfs_realtime_pb2 as pb
from test_reconstruction import gps_catalog as previous_catalog
from test_reconstruction import gps_catalog_path as previous_path
from test_reconstruction import scenario

from transmitracker.catalog.common import file_hash
from transmitracker.profiles.models import Profile, ProfileKind
from transmitracker.profiles.store import ProfileStore
from transmitracker.reconstruction.__main__ import main
from transmitracker.reconstruction.engine import ReconstructionEngine
from transmitracker.reconstruction.io import read_saved_capture, snapshot_from_rows
from transmitracker.reconstruction.models import Parameters
from transmitracker.reconstruction.providers import CreditPolicy
from transmitracker.reconstruction.store import EvidenceStore

gps_catalog = previous_catalog
gps_catalog_path = previous_path


def test_store_roundtrip_dedup_and_algorithm_reprocessing(gps_catalog, tmp_path, monkeypatch):
    case = scenario(gps_catalog)
    result = ReconstructionEngine(gps_catalog).run(
        case.snapshots, legs=case.legs, evidence=case.evidence
    )
    path = tmp_path / "evidence.sqlite3"
    with EvidenceStore(path) as store:
        first = store.save(result)
        counts = store.connection.execute("SELECT COUNT(*) FROM originals").fetchone()[0]
        changes = store.connection.total_changes
        assert store.save(result) == {"run_id": first["run_id"], "reused": True}
        assert store.connection.total_changes == changes
        assert store.load_snapshot(case.snapshots[0].snapshot_id) == case.snapshots[0]
        different = ReconstructionEngine(gps_catalog, Parameters(gps_error_m=10)).run(
            case.snapshots, legs=case.legs, evidence=case.evidence
        )
        assert store.save(different)["run_id"] != first["run_id"]
        # Simulate the next engine release in a test, retaining all originals and prior results.
        monkeypatch.setattr(
            "transmitracker.reconstruction.engine.ALGORITHM_VERSION", "gps-offline-future-test"
        )
        future = ReconstructionEngine(gps_catalog).run(
            case.snapshots, legs=case.legs, evidence=case.evidence
        )
        store.save(future)
        assert store.connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 3
        assert store.connection.execute("SELECT COUNT(*) FROM originals").fetchone()[0] == counts
        assert not store.connection.execute("PRAGMA foreign_key_check").fetchall()
        assert store.connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert store.connection.execute("SELECT version FROM engine_migrations").fetchone()[0] == 1
    before = file_hash(path)
    with EvidenceStore(path) as store:
        assert store.save(result)["reused"]
    assert file_hash(path) == before


def test_store_refuses_catalog_and_profile_databases_without_writes(gps_catalog_path, tmp_path):
    before = file_hash(gps_catalog_path)
    with pytest.raises(ValueError, match="Refusing"):
        EvidenceStore(gps_catalog_path)
    assert file_hash(gps_catalog_path) == before
    path = tmp_path / "profiles.sqlite3"
    with ProfileStore(path):
        pass
    before = file_hash(path)
    with pytest.raises(ValueError):
        EvidenceStore(path)
    assert file_hash(path) == before


def test_duplicate_frames_are_not_new_motion(gps_catalog):
    case = scenario(gps_catalog)
    frames = (case.snapshots[0], *case.snapshots)
    result = ReconstructionEngine(gps_catalog).run(frames, legs=case.legs, evidence=case.evidence)
    assert "duplicate_snapshot_input" in result.input_order_warnings
    assert sum(m.accepted for m in result.measurements) == 1
    assert len(result.projections) == len(case.snapshots)


def saved_capture(tmp_path, gps_catalog, *, verified=False):
    feed = pb.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = 1794488400
    entity = feed.entity.add(id="DEMO_ENTITY")
    vehicle = entity.vehicle
    vehicle.vehicle.id = "DEMO_V1"
    vehicle.position.latitude = 4.65
    vehicle.position.longitude = -74.06
    vehicle.position.speed = 0  # Explicit zero is preserved separately from an assumed velocity.
    vehicle.trip.trip_id = "DEMO_TRIP_LINE"
    vehicle.trip.route_id = "DEMO_LINE"
    vehicle.trip.start_date = "20261112"
    vehicle.trip.start_time = "08:00:00"
    vehicle.stop_id = "DEMO_LINE_A"
    vehicle.current_stop_sequence = 10
    payload = feed.SerializeToString()
    (tmp_path / "positions.pb").write_bytes(payload)
    path = tmp_path / "capture.json"
    path.write_text(
        json.dumps(
            {
                "origin": "saved_real_snapshot",
                "source": "https://provider.invalid/positions.pb",
                "received_at": "2026-11-12T08:00:01-05:00",
                "receipt_timestamp_verified": verified,
                "raw_file": "positions.pb",
                "payload_sha256": hashlib.sha256(payload).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    return path


def test_saved_capture_no_invented_receipt_report_or_status(gps_catalog, tmp_path):
    path = saved_capture(tmp_path, gps_catalog)
    snapshot = read_saved_capture(path, gps_catalog.info()["sha256"])
    assert snapshot.received_at is None and snapshot.receipt_reference_at is not None
    assert snapshot.observations[0].reported_at is None
    assert (
        snapshot.observations[0].current_status is None
    )  # No protobuf default IN_TRANSIT_TO is invented.
    raw = json.loads(snapshot.observations[0].raw_json)
    assert raw["protobuf_vehicle"]["position"]["speed"] == 0
    result = ReconstructionEngine(gps_catalog).run((snapshot,))
    assert not result.projections and not result.measurements
    assert any(r.reason == "missing_or_invalid_vehicle_timestamp" for r in result.rejections)
    with EvidenceStore(tmp_path / "evidence.sqlite3") as store:
        store.save(result)
        assert store.load_snapshot(snapshot.snapshot_id) == snapshot


def test_capture_hash_and_path_integrity(gps_catalog, tmp_path):
    path = saved_capture(tmp_path, gps_catalog)
    (tmp_path / "positions.pb").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        read_saved_capture(path, gps_catalog.info()["sha256"])
    record = json.loads(path.read_text(encoding="utf-8"))
    record["raw_file"] = "../outside.pb"
    path.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="directory"):
        read_saved_capture(path, gps_catalog.info()["sha256"])


def test_numeric_identifier_not_coerced(gps_catalog):
    with pytest.raises(ValueError, match="strings"):
        snapshot_from_rows(
            source="synthetic",
            endpoint=None,
            catalog_sha256=gps_catalog.info()["sha256"],
            origin="synthetic_fixture",
            rows=[{"vehicle_id": 123}],
        )


def test_cli_synthetic_replay_idempotent(gps_catalog_path, tmp_path, capsys):
    report = tmp_path / "report.json"
    database = tmp_path / "reconstruction.sqlite3"
    command = [
        "replay",
        "--catalog",
        str(gps_catalog_path),
        "--scenario",
        "normal",
        "--db",
        str(database),
        "--output",
        str(report),
    ]
    assert main(command) == 0
    first = json.loads(report.read_text(encoding="utf-8"))
    assert first["accepted_measurements"] == 1 and not first["reused"]
    assert first["network_requests"] == 0 and not first["real_operational_validation"]
    assert main(command) == 0
    assert json.loads(report.read_text(encoding="utf-8"))["reused"]
    assert "network_requests" in capsys.readouterr().out


def test_cli_reuses_structural_profile_read_only(gps_catalog, gps_catalog_path, tmp_path):
    from datetime import time

    case = scenario(gps_catalog)
    path = tmp_path / "profiles.sqlite3"
    profile = Profile(
        "DEMO_PROFILE",
        ProfileKind.TO_WORK,
        gps_catalog.info()["sha256"],
        case.legs,
        (),
        0,
        0,
        time(10),
        time(7),
        tuple(range(7)),
    )
    with ProfileStore(path) as store:
        assert store.register_catalog(gps_catalog_path).ok
        assert store.save_configuration(profile).ok
    original = file_hash(path)
    output = tmp_path / "output.json"
    assert (
        main(
            [
                "replay",
                "--catalog",
                str(gps_catalog_path),
                "--scenario",
                "normal",
                "--profiles-db",
                str(path),
                "--profile-id",
                profile.profile_id,
                "--db",
                str(tmp_path / "offline.sqlite3"),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    assert file_hash(path) == original
    assert json.loads(output.read_text(encoding="utf-8"))["accepted_measurements"] == 1


def test_wrong_target_occurrences_and_catalog_hash_rejected(gps_catalog):
    case = scenario(gps_catalog)
    engine = ReconstructionEngine(gps_catalog)
    with pytest.raises(ValueError):
        engine.run(case.snapshots, legs=(replace(case.legs[0], destination_sequence=1),))
    with pytest.raises(ValueError, match="hash"):
        engine.run((replace(case.snapshots[0], catalog_sha256="0" * 64),))


def test_budget_is_only_a_configurable_contract_not_endpoint_classification():
    policy = CreditPolicy()
    assert (policy.monthly_credits, policy.live_cost, policy.dataset_cost) == (1500, 10, 1)
    assert not policy.operation_classification_verified
