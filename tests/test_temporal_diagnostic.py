import json
from datetime import datetime, timedelta

import httpx
import pytest

from transmitracker.catalog.common import BOGOTA
from transmitracker.catalog.importer import import_catalog
from transmitracker.catalog.queries import Catalog
from transmitracker.research.scenarios import synthetic_snapshots
from transmitracker.research.snapshot_diagnostic import (
    ENDPOINT,
    check_review,
    collect,
    validate_limits,
)
from transmitracker.research.temporal import TemporalAnalyzer, capture_record, project


@pytest.fixture(scope="module")
def temporal_catalog(tmp_path_factory):
    from pathlib import Path

    source = Path(__file__).parent / "fixtures/synthetic_gtfs.zip"
    path = tmp_path_factory.mktemp("temporal") / "catalog.sqlite3"
    import_catalog(source, path)
    return path


@pytest.fixture
def frames(fixture_dir):
    scenario = json.loads((fixture_dir / "phase1b_temporal.json").read_text(encoding="utf-8"))
    return [(clock, payload) for clock, payload in synthetic_snapshots(scenario)]


def records(frames):
    return [
        capture_record(
            payload, received_at=clock, source="synthetic://fixture", origin="synthetic_fixture"
        )
        for clock, payload in frames
    ]


def test_start_time_evolution_and_stable_vehicle_comparison(temporal_catalog, frames):
    with Catalog(temporal_catalog) as catalog:
        result = TemporalAnalyzer(catalog).analyze(records(frames))
    assert result["compared_vehicle_pairs"] == 4
    assert result["field_change_counts"]["start_time"] == 2
    assert result["field_change_counts"].get("trip_id", 0) == 0
    assert not result["real_temporal_validation"]
    assert not result["operational_identity_validated"]
    assert result["arrivals_inferred"] == result["travel_durations_inferred"] == 0
    changed = [p for p in result["pairs"] if p["start_time_changed_with_new_gps"]]
    assert len(changed) == 2
    assert all(p["start_time_equals_gps_clock"] for p in changed)
    assert all(p["association"]["classification"] == "ambiguous" for p in changed)
    assert any(p.get("geometric_progress") == "forward" for p in result["pairs"])


def test_all_four_association_classes(temporal_catalog, frames):
    _, payload = frames[0]
    capture = records(frames)[0]
    valid = capture["vehicles"][0]
    with Catalog(temporal_catalog) as catalog:
        analyzer = TemporalAnalyzer(catalog)
        assert analyzer.association(valid)["classification"] == "verified"
        assert (
            analyzer.association({**valid, "current_stop_sequence": None})["classification"]
            == "ambiguous"
        )
        assert (
            analyzer.association({**valid, "route_id": "DEMO_R2"})["classification"]
            == "contradictory"
        )
        assert (
            analyzer.association({**valid, "trip_id": "UNKNOWN"})["classification"] == "unresolved"
        )
        assert (
            analyzer.association({**valid, "stop_id": "DEMO_S2"})["reason"]
            == "stop_sequence_conflict"
        )


def test_stale_replay_and_one_real_capture_do_not_prove_temporal_identity(temporal_catalog, frames):
    clock, payload = frames[0]
    capture = capture_record(
        payload, received_at=clock, source=ENDPOINT, origin="saved_real_snapshot"
    )
    with Catalog(temporal_catalog) as catalog:
        analyzer = TemporalAnalyzer(catalog)
        report = analyzer.analyze([capture])
        assert not report["real_temporal_validation"]
        repeated = analyzer.analyze(
            [capture, {**capture, "received_at": (clock + timedelta(seconds=60)).isoformat()}]
        )
        assert not repeated["real_temporal_validation"]
        assert all(
            p["trajectory_status"] == "unchanged_gps_timestamp_not_new_movement"
            for p in repeated["pairs"]
        )
        stale = capture_record(
            payload,
            received_at=clock + timedelta(hours=1),
            source=ENDPOINT,
            origin="saved_real_snapshot",
        )
        assert analyzer.analyze([stale])["reference_associations"] == {"unresolved": 2}


def test_no_mixing_real_and_synthetic_or_provider_namespaces(temporal_catalog, frames):
    captures = records(frames)
    with Catalog(temporal_catalog) as catalog:
        analyzer = TemporalAnalyzer(catalog)
        with pytest.raises(ValueError, match="separately"):
            analyzer.analyze([captures[0], {**captures[1], "origin": "saved_real_snapshot"}])
        assert (
            analyzer.analyze(
                [captures[0], {**captures[1], "source": "synthetic://other-provider"}]
            )["compared_vehicle_pairs"]
            == 0
        )


def test_projection_and_nonunique_loop_are_not_confused():
    assert project((4.655, -74.055), ((4.65, -74.06), (4.66, -74.05)))["progress_m"] > 0
    assert project((4.65, -74.06), ()) is None
    loop = ((4.65, -74.06), (4.66, -74.05), (4.65, -74.06))
    assert project((4.65, -74.06), loop)["ambiguous_projection"]


@pytest.mark.parametrize("count,interval", [(1, 60), (17, 60), (3, 59), (16, 61), (2, 901)])
def test_bounded_limits(count, interval):
    with pytest.raises(ValueError):
        validate_limits(count, interval)


def review():
    return {
        "decision": "bounded_test_allowed",
        "endpoint": ENDPOINT,
        "reviewed_at": datetime.now(BOGOTA).isoformat(),
        "minimum_interval_seconds": 60,
        "maximum_captures": 16,
        "evidence": "synthetic authorization fixture, not provider permission",
    }


def test_unknown_conditions_block_before_any_http(tmp_path):
    with pytest.raises(ValueError, match="conditions"):
        collect({"decision": "not_established"}, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()
    with pytest.raises(ValueError):
        check_review({**review(), "endpoint": "https://other.invalid"}, 3, 60)


def test_capture_has_minimum_interval_no_retry_and_full_provenance(tmp_path, frames):
    ticks = [0.0]
    starts = []
    base = frames[0][0]

    def handler(request):
        starts.append(ticks[0])
        if len(starts) == 3:
            return httpx.Response(429, headers={"Retry-After": "300"})
        return httpx.Response(200, content=frames[len(starts) - 1][1])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        captures = collect(
            review(),
            tmp_path / "run",
            count=3,
            interval=60,
            clock=lambda: ticks[0],
            sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds),
            now=lambda: base + timedelta(seconds=ticks[0]),
            client=client,
        )
    assert starts == [0, 60, 120]
    assert len(captures) == 2
    assert captures[0]["payload_sha256"]
    assert captures[0]["source"] == ENDPOINT
    assert captures[0]["received_at"]
    assert captures[0]["feed"]["timestamp"]
    assert captures[0]["vehicles"][0]["reported"]["timestamp"]
    assert captures[0]["vehicles"][0]["current_stop_sequence"] == 1
    assert captures[0]["vehicles"][0]["current_status"]
    run = json.loads((tmp_path / "run/run.json").read_text())
    assert run["failures"][0]["download"]["status"] == 429
    assert run["failures"][0]["download"]["attempts"] == 1


def test_change_of_trip_and_sequence_regression_are_reported(temporal_catalog, frames):
    data = records(frames)
    data[1]["vehicles"][0]["trip_id"] = "NEW_TRIP"
    data[1]["vehicles"][0]["current_stop_sequence"] = 0
    with Catalog(temporal_catalog) as catalog:
        result = TemporalAnalyzer(catalog).analyze(data)
    assert result["field_change_counts"]["trip_id"] >= 1
    assert any(p["sequence_progress"] == "reverse" for p in result["pairs"])


def test_disappearance_is_not_an_arrival_or_a_renumbering(temporal_catalog, frames):
    data = records(frames)
    data[-1]["vehicles"] = data[-1]["vehicles"][:1]
    with Catalog(temporal_catalog) as catalog:
        report = TemporalAnalyzer(catalog).analyze(data)
    assert report["vehicle_cohort_transitions"][-1]["disappeared_vehicle_ids"] == ["DEMO_TEMP_V2"]
    assert report["arrivals_inferred"] == 0


def test_maximum_capture_plan_stops_before_15_minute_deadline(tmp_path, frames):
    ticks = [0.0]
    starts = []

    def handler(request):
        starts.append(ticks[0])
        return httpx.Response(200, content=frames[0][1])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        captures = collect(
            review(),
            tmp_path / "bounded",
            count=16,
            interval=60,
            clock=lambda: ticks[0],
            sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds),
            now=lambda: frames[0][0] + timedelta(seconds=ticks[0]),
            client=client,
        )
    assert len(captures) <= 16
    assert ticks[0] <= 900
    assert all(second - first >= 60 for first, second in zip(starts, starts[1:], strict=False))
    assert (
        json.loads((tmp_path / "bounded/run.json").read_text())["failures"][0]["reason"]
        == "deadline_reserve_reached"
    )
