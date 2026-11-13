"""Offline profile examples and separately labeled real/synthetic snapshot analysis."""

import json
from dataclasses import replace
from datetime import datetime, time
from pathlib import Path
from uuid import uuid4

from transmitracker.catalog.common import file_hash
from transmitracker.catalog.importer import import_catalog
from transmitracker.catalog.queries import Catalog
from transmitracker.profiles.contracts import primitive
from transmitracker.profiles.models import Leg, Profile, ProfileKind, Transfer
from transmitracker.profiles.services import CatalogService
from transmitracker.profiles.store import ProfileStore
from transmitracker.research.scenarios import synthetic_snapshots
from transmitracker.research.temporal import TemporalAnalyzer, capture_record

ROOT = Path(__file__).resolve().parents[1]


def write_report(name, report):
    (ROOT / "docs" / name).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main():
    work = ROOT / "data/phase1b"
    work.mkdir(parents=True, exist_ok=True)
    database = ROOT / "data/catalog/official_20261112.sqlite3"
    before = (file_hash(database), database.stat().st_mtime_ns)
    previous_demo = json.loads((ROOT / "docs/PHASE1A_DEMO.json").read_text(encoding="utf-8"))
    choice = previous_demo["demonstration"]["selection"]
    destination = previous_demo["demonstration"]["destinations"][0]
    second_destination = previous_demo["demonstration"]["destinations"][1]
    clock = datetime.fromisoformat("2026-11-12T08:00:00-05:00")
    store_path = work / ("profiles_demo_" + uuid4().hex + ".sqlite3")
    with Catalog(database) as catalog, ProfileStore(store_path) as store:
        service = CatalogService(catalog)
        leg = Leg(
            choice["origin_platform_id"],
            choice["route_id"],
            choice["pattern_id"],
            choice["direction_id"],
            choice["origin_sequence"],
            destination["stop_id"],
            destination["sequence"],
        )
        profile = Profile(
            "example-to-work",
            ProfileKind.TO_WORK,
            catalog.info()["sha256"],
            (leg,),
            (),
            2,
            5,
            time(9),
            time(7, 30),
            (0, 1, 2, 3, 4),
            3,
        )
        assert store.register_catalog(database).ok
        assert store.activate_catalog(profile.catalog_sha256, changed_at=clock).ok
        saved = store.save(profile, departure_at=clock)
        assert saved.ok, saved.to_dict()
        returning = replace(
            profile,
            profile_id="example-to-home",
            kind=ProfileKind.TO_HOME,
            arrival_deadline=time(18),
            notification_time=time(16, 30),
        )
        saved_return = store.save(returning, departure_at=clock.replace(hour=17))
        assert saved_return.ok, saved_return.to_dict()
        second = replace(
            leg,
            origin_stop_id=destination["stop_id"],
            origin_sequence=destination["sequence"],
            destination_stop_id=second_destination["stop_id"],
            destination_sequence=second_destination["sequence"],
        )
        connected = replace(
            profile, legs=(leg, second), transfers=(Transfer(7, 2),), arrival_deadline=time(10)
        )
        checks = {
            "valid_to_work": service.validate(profile, clock).to_dict(),
            "valid_to_home": service.validate(returning, clock.replace(hour=17)).to_dict(),
            "two_legs_user_transfer": service.validate(connected, clock).to_dict(),
            "invalid_direction": service.validate(
                replace(profile, legs=(replace(leg, direction_id=0),)), clock
            ).to_dict(),
            "invalid_deadline": service.validate(
                replace(profile, arrival_deadline=time(7)), clock
            ).to_dict(),
            "invalid_sequence": service.validate(
                replace(profile, legs=(replace(leg, destination_sequence=1),)), clock
            ).to_dict(),
        }
        assert checks["two_legs_user_transfer"]["ok"]
        write_report(
            "PHASE1B_PROFILE_EXAMPLES.json",
            {
                "origin": "technical_profile_examples_using_real_static_catalog_not_user_commutes",
                "network_requests": 0,
                "profile_database": store_path.relative_to(ROOT).as_posix(),
                "profiles": [primitive(profile), primitive(returning)],
                "transfer_example": primitive(connected),
                "validation_examples": checks,
                "persisted_revisions": [
                    store.load(profile.profile_id).data.revision,
                    store.load(returning.profile_id).data.revision,
                ],
            },
        )
        original = json.loads((ROOT / "docs/LIVE_DIAGNOSTIC.json").read_text(encoding="utf-8"))
        entry = next(e for e in original["results"] if e["name"] == "official_positions")
        payload = (ROOT / "data/probes/official_positions.pb").read_bytes()
        record = capture_record(
            payload,
            received_at=datetime.fromisoformat(entry["download"]["queried_at"]),
            source=entry["url"],
            origin="saved_real_snapshot",
            receipt_timestamp_verified=False,
        )
        assert record["payload_sha256"] == entry["download"]["sha256"]
        record["time_reference_kind"] = (
            "original_request_start_reference_exact_receipt_not_recorded_in_phase0"
        )
        evidence = work / "saved_original"
        evidence.mkdir(exist_ok=True)
        (evidence / "positions.pb").write_bytes(payload)
        record["raw_file"] = "positions.pb"
        (evidence / "capture.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        result = TemporalAnalyzer(catalog).analyze([record])
        result["time_reference_kind"] = record["time_reference_kind"]
        write_report("PHASE1B_REAL_SAVED_ANALYSIS.json", result)
    assert (file_hash(database), database.stat().st_mtime_ns) == before
    synthetic_db = work / "synthetic_catalog.sqlite3"
    import_catalog(ROOT / "tests/fixtures/synthetic_gtfs.zip", synthetic_db)
    scenario = json.loads(
        (ROOT / "tests/fixtures/phase1b_temporal.json").read_text(encoding="utf-8")
    )
    captures = []
    folder = work / "synthetic_captures"
    folder.mkdir(exist_ok=True)
    for index, (clock, payload) in enumerate(synthetic_snapshots(scenario)):
        record = capture_record(
            payload, received_at=clock, source="synthetic://phase1b", origin="synthetic_fixture"
        )
        record["raw_file"] = f"snapshot_{index}.pb"
        (folder / record["raw_file"]).write_bytes(payload)
        (folder / f"snapshot_{index}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        captures.append(record)
    with Catalog(synthetic_db) as catalog:
        result = TemporalAnalyzer(catalog).analyze(captures)
        write_report("PHASE1B_SYNTHETIC_TEMPORAL.json", result)
    print("Saved profile examples and separately labeled temporal evidence. Network requests: 0.")
    print("Synthetic field changes:", result["field_change_counts"])
    print("Synthetic pair associations:", result["temporal_associations"])
    print("Real catalog unchanged: True")


if __name__ == "__main__":
    main()
