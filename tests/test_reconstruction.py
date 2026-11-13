"""Offline GPS reconstruction against known, explicitly synthetic truth."""

import json
import math

import pytest

from transmitracker.catalog.queries import Catalog
from transmitracker.reconstruction.engine import ReconstructionEngine
from transmitracker.reconstruction.evaluation import evaluate_case
from transmitracker.reconstruction.geometry import GeometryCatalog, MeasuredShape
from transmitracker.reconstruction.io import snapshot_from_rows
from transmitracker.reconstruction.models import Confidence, EventKind, Parameters
from transmitracker.reconstruction.scenarios import build_case, create_catalog, specs


@pytest.fixture(scope="module")
def gps_catalog_path(tmp_path_factory):
    return create_catalog(tmp_path_factory.mktemp("synthetic_gps_catalog"))


@pytest.fixture
def gps_catalog(gps_catalog_path):
    with Catalog(gps_catalog_path) as catalog:
        yield catalog


def scenario(catalog, name="normal", gap=20):
    return build_case(catalog, next(s for s in specs() if s["name"] == name), gap)


def alter(snapshot, index=0, changes=None, **header):
    rows = [json.loads(o.raw_json) for o in snapshot.observations]
    if changes:
        rows[index].update(changes)
    arguments = {
        "source": snapshot.source,
        "endpoint": snapshot.endpoint,
        "catalog_sha256": snapshot.catalog_sha256,
        "origin": snapshot.origin,
        "rows": rows,
        "feed_as_of": snapshot.feed_as_of,
        "received_at": snapshot.received_at,
        "receipt_reference_at": snapshot.receipt_reference_at,
        "complete": snapshot.complete,
    }
    arguments.update(header)
    return snapshot_from_rows(**arguments)


@pytest.mark.parametrize("spec", specs(), ids=lambda s: s["name"])
def test_scenario_truth_and_safety(gps_catalog, spec):
    case = build_case(gps_catalog, spec)
    result = ReconstructionEngine(gps_catalog).run(
        case.snapshots, legs=case.legs, evidence=case.evidence
    )
    evaluation = evaluate_case(case, result, gps_catalog)
    assert not result.real_operational_validation
    assert all(not s.identity.operationally_verified for s in result.segments)
    assert evaluation["proposed"]["false_positives"] == 0
    assert evaluation["unsafe_accepted_measurements"] == 0
    if not case.must_reject_measurement:
        assert evaluation["accepted_measurements"] >= 1
    else:
        assert not any(m.accepted for m in result.measurements)
    assert not any(e.kind == EventKind.ARRIVAL for e in result.events)
    for measurement in result.measurements:
        assert measurement.waiting_time_s is None and measurement.walking_time_s is None
        if measurement.accepted:
            assert (
                measurement.duration_min_s
                <= measurement.estimated_duration_s
                <= measurement.duration_max_s
            )


@pytest.mark.parametrize("gap", [20, 40, 90])
def test_precision_intervals_and_duration_bounds(gps_catalog, gap):
    case = scenario(gps_catalog, gap=gap)
    result = ReconstructionEngine(gps_catalog).run(
        case.snapshots, legs=case.legs, evidence=case.evidence
    )
    evaluation = evaluate_case(case, result, gps_catalog)
    assert evaluation["proposed"]["detected_percent"] == 100
    assert evaluation["proposed"]["uncertainty_interval_coverage_percent"] == 100
    crossings = [
        e for e in result.events if e.accepted and e.kind == EventKind.CROSSING and e.sequence <= 30
    ]
    assert len(crossings) == 3
    if gap == 90:
        assert all(e.estimated_at is None for e in crossings)
        assert not any(m.accepted for m in result.measurements)
        assert "duration_uncertainty_too_wide" in result.measurements[0].reasons
        assert evaluation["proposed"]["median_absolute_error_s"] is None
        assert evaluation["proposed"]["interval_midpoint_proxy_median_error_s"] is not None
    else:
        assert evaluation["proposed"]["median_absolute_error_s"] < 0.001
        assert (
            evaluation["proposed"]["detected_percent"] >= evaluation["baseline"]["detected_percent"]
        )
        assert (
            evaluation["proposed"]["median_absolute_error_s"]
            < evaluation["baseline"]["median_absolute_error_s"]
        )
        measurement = next(m for m in result.measurements if m.accepted)
        assert measurement.estimated_duration_s == pytest.approx(70, abs=0.001)


def test_noise_has_known_nonzero_error_not_perfect_real_claim(gps_catalog):
    case = scenario(gps_catalog, "bounded_gps_noise")
    result = ReconstructionEngine(gps_catalog).run(
        case.snapshots, legs=case.legs, evidence=case.evidence
    )
    metrics = evaluate_case(case, result, gps_catalog)["proposed"]
    assert 0 < metrics["median_absolute_error_s"] < 1
    assert metrics["p90_absolute_error_s"] < 2


def test_synthetic_label_alone_does_not_prove_identity(gps_catalog):
    case = scenario(gps_catalog)
    result = ReconstructionEngine(gps_catalog).run(case.snapshots, legs=case.legs)
    assert not any(e.accepted for e in result.events)
    assert not any(m.accepted for m in result.measurements)
    assert all(s.identity.confidence == Confidence.CANDIDATE for s in result.segments)


def test_real_identity_can_never_be_authorized_by_synthetic_claim(gps_catalog):
    case = scenario(gps_catalog)
    real = tuple(alter(s, origin="saved_real_snapshot") for s in case.snapshots)
    engine = ReconstructionEngine(gps_catalog)
    with pytest.raises(ValueError, match="Synthetic identity"):
        engine.run(real, evidence=case.evidence)
    result = engine.run(real, legs=case.legs)
    assert not any(m.accepted for m in result.measurements)
    assert not any(s.identity.operationally_verified for s in result.segments)
    with pytest.raises(ValueError, match="separate batches"):
        engine.run((real[0], case.snapshots[0]))


def test_loop_stop_occurrences_not_collapsed_and_baseline_false_positive(gps_catalog):
    case = scenario(gps_catalog, "loop_repeated_stop")
    result = ReconstructionEngine(gps_catalog).run(
        case.snapshots, legs=case.legs, evidence=case.evidence
    )
    measurements = [m for m in result.measurements if m.accepted]
    assert len(measurements) == 1
    measurement = measurements[0]
    assert measurement.origin_stop_id == measurement.destination_stop_id
    assert (measurement.origin_sequence, measurement.destination_sequence) == (10, 30)
    assert measurement.estimated_duration_s == pytest.approx(160, abs=0.01)
    assert evaluate_case(case, result, gps_catalog)["baseline"]["false_positives"] >= 1


def test_stationarity_is_not_observed_arrival(gps_catalog):
    case = scenario(gps_catalog, "stopped")
    result = ReconstructionEngine(gps_catalog).run(
        case.snapshots, legs=case.legs, evidence=case.evidence
    )
    stationary = [e for e in result.events if e.kind == EventKind.STOP]
    assert len(stationary) == 1 and len(stationary[0].support_ids) >= 3
    assert stationary[0].estimated_at is None
    assert "not_arrival" in stationary[0].method
    assert all(e.kind != EventKind.ARRIVAL for e in result.events)


def test_two_vehicles_same_trip_and_route_remain_distinct(gps_catalog):
    case = scenario(gps_catalog, "two_buses_same_route")
    result = ReconstructionEngine(gps_catalog).run(
        case.snapshots, legs=case.legs, evidence=case.evidence
    )
    assert (
        len(result.targets) == 1
    )  # shared target is processed once per physical synthetic vehicle
    assert len({s.identity.identity_id for s in result.segments}) == 2
    assert sum(m.accepted for m in result.measurements) == 2


def test_large_input_reordering_is_not_a_clock_reset(gps_catalog):
    case = scenario(gps_catalog, gap=90)
    result = ReconstructionEngine(gps_catalog).run(
        tuple(reversed(case.snapshots)), legs=case.legs, evidence=case.evidence
    )
    assert "input_report_out_of_order" in result.input_order_warnings
    assert not any("clock_reset" in r.reason for r in result.rejections)
    assert sum(e.accepted and e.kind == EventKind.CROSSING for e in result.events) >= 3


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"reported_at": None}, "missing_or_invalid_vehicle_timestamp"),
        ({"latitude": float("nan")}, "invalid_or_missing_coordinates"),
        ({"vehicle_id": None}, "missing_vehicle_id_no_entity_fallback"),
        ({"start_time": "broken"}, "invalid_start_time"),
        ({"current_stop_sequence": True}, "invalid_stop_sequence"),
        (
            {"position_kind": "visual_extrapolation"},
            "visual_or_extrapolated_position_is_not_gps_evidence",
        ),
    ],
)
def test_invalid_fields_not_filled_from_other_timestamps(gps_catalog, changes, reason):
    case = scenario(gps_catalog)
    snapshot = alter(case.snapshots[0], changes=changes)
    result = ReconstructionEngine(gps_catalog).run((snapshot,))
    assert any(r.reason == reason for r in result.rejections)
    assert not result.projections
    if changes.get("reported_at", 1) is None:
        assert result.normalized[0].reported_at is None


def test_feed_age_future_and_regression(gps_catalog):
    case = scenario(gps_catalog)
    frames = list(case.snapshots)
    frames[2] = alter(frames[2], feed_as_of=frames[0].feed_as_of - 1)
    result = ReconstructionEngine(gps_catalog).run(frames)
    assert any(
        r.reason == "feed_timestamp_regressed_under_verified_receipt_order"
        for r in result.rejections
    )
    future = alter(case.snapshots[0], feed_as_of=case.snapshots[0].received_at + 30)
    result = ReconstructionEngine(gps_catalog).run((future,))
    assert any(r.reason == "future_feed_timestamp" for r in result.rejections)


def test_incomplete_snapshots_do_not_imply_disappearance(gps_catalog):
    case = scenario(gps_catalog, "missing_snapshots")
    snapshots = tuple(alter(s, complete=False) if not s.observations else s for s in case.snapshots)
    result = ReconstructionEngine(gps_catalog).run(
        snapshots, legs=case.legs, evidence=case.evidence
    )
    assert not any(r.reason == "disappeared_between_complete_snapshots" for r in result.rejections)
    assert any(m.accepted for m in result.measurements)


def test_gap_threshold_and_conflicting_descriptor_no_suffix_matching(gps_catalog):
    case = scenario(gps_catalog)
    result = ReconstructionEngine(gps_catalog, Parameters(max_gap_s=10)).run(
        case.snapshots, legs=case.legs, evidence=case.evidence
    )
    assert any(r.reason == "observation_gap" for r in result.rejections)
    assert not any(m.accepted for m in result.measurements)
    altered = alter(case.snapshots[0], changes={"trip_id": "invented.1.DEMO_LINE"})
    result = ReconstructionEngine(gps_catalog).run((altered,))
    assert any(r.reason == "trip_id_not_in_catalog" for r in result.rejections)
    assert not result.segments


def test_branch_patterns_multiple_geometries_and_midnight(gps_catalog):
    line, branch = scenario(gps_catalog), scenario(gps_catalog, "branch_trip")
    assert line.legs[0].route_id == branch.legs[0].route_id
    assert line.legs[0].pattern_id != branch.legs[0].pattern_id
    case = scenario(gps_catalog, "midnight")
    result = ReconstructionEngine(gps_catalog).run(
        case.snapshots, legs=case.legs, evidence=case.evidence
    )
    assert any(m.accepted for m in result.measurements)
    assert all(o.start_date == "20261112" for s in result.snapshots for o in s.observations)
    assert result.segments[0].ended_at - result.segments[0].started_at > 30


def test_gtfs_distance_units_not_assumed_metres_and_ambiguity_preserved(gps_catalog):
    measured = MeasuredShape([(4.65, -74.06), (4.65, -74.05)], [0, 1])
    assert measured.published_progress(0.5) == pytest.approx(measured.along[-1] / 2)
    assert measured.published_progress(2) is None
    case = scenario(gps_catalog, "loop_repeated_stop")
    geometry = GeometryCatalog(gps_catalog, Parameters()).load(
        case.snapshots[0].observations[0].trip_id
    )
    assert geometry.stops[2].progress_m > geometry.stops[0].progress_m + 1000
    with pytest.raises(ValueError):
        Parameters(max_gap_s=math.inf)
    with pytest.raises(ValueError):
        Parameters(gps_error_m=-1)
