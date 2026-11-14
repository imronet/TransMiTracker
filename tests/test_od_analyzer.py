"""Candidate-only OD cases from the unchanged tracker and synthetic GTFS catalog."""

import copy
import json
import shutil

import pytest

from transmitracker.catalog.queries import Catalog
from transmitracker.reconstruction.io import snapshot_from_rows
from transmitracker.reconstruction.models import Parameters
from transmitracker.reconstruction.scenarios import create_catalog, ll, point_at
from transmitracker.research import od_analyzer as od
from transmitracker.research.route_tracker import RouteGeometry, track


@pytest.fixture(scope="module")
def catalog_path(tmp_path_factory):
    return create_catalog(tmp_path_factory.mktemp("od-synthetic-catalog"))


@pytest.fixture
def catalog(catalog_path):
    with Catalog(catalog_path) as result:
        yield result


def pattern(catalog, path="line"):
    return catalog.connection.execute(
        "SELECT pattern_id FROM trips WHERE trip_id=?", ("DEMO_TRIP_" + path.upper(),)
    ).fetchone()[0]


def report(
    catalog,
    positions=(0, 200, 300, 500, 600),
    times=(0, 20, 30, 50, 60),
    *,
    path="line",
    other_routes=(),
    with_geometry=False,
):
    route = "DEMO_LINE" if path == "branch" else "DEMO_" + path.upper()
    snapshots = []
    for index, (progress, seconds) in enumerate(zip(positions, times, strict=True)):
        lat, lon = ll(point_at(path, progress))
        row = {
            "vehicle_id": "DEMO_VEHICLE",
            "route_id": "DEMO_OTHER" if index in other_routes else route,
            "latitude": lat,
            "longitude": lon,
            "reported_at": 1800000000 + seconds,
            "trip_id": "PUBLISHED_NO_STATIC_MATCH_" + str(index),
            "start_time": str(seconds),
            "start_date": "20261114",
            "stop_id": "AUXILIARY_UNKNOWN",
            "current_stop_sequence": 999,
        }
        snapshots.append(
            snapshot_from_rows(
                source="synthetic://od",
                endpoint=None,
                catalog_sha256=catalog.info()["sha256"],
                origin="synthetic_fixture",
                rows=[row],
                received_at=1800000005 + seconds,
                feed_as_of=1800000005 + seconds,
            )
        )
    result = track(
        snapshots,
        route,
        geometry=RouteGeometry(catalog, route, Parameters(max_gap_s=300))
        if with_geometry
        else None,
    )
    result.update(origins=["synthetic_fixture"], catalog=catalog.info())
    return result


def analyze(catalog, payload=None, **kwargs):
    return od.analyze(
        payload or report(catalog),
        catalog,
        "DEMO_LINE",
        pattern(catalog),
        "DEMO_LINE_A",
        "DEMO_LINE_B",
        **kwargs,
    )


def segments(result):
    return [s for candidate in result["candidates"] for s in candidate["segments"]]


def test_crossings_and_candidate_interval_reuse_3a_without_operational_acceptance(catalog):
    result = analyze(catalog)
    assert result["summary"]["crossing_candidates"] == 2
    assert result["summary"]["duration_candidates"] == 1
    segment = segments(result)[0]
    duration = segment["duration"]
    assert duration["duration_min_s"] == pytest.approx(8)
    assert duration["duration_max_s"] == pytest.approx(52)
    assert duration["estimated_duration_s"] == pytest.approx(30, abs=0.01)
    assert duration["uncertainty_s"] == pytest.approx(44)
    assert not duration["conservative_3a_accepted"]
    assert "operational_identity_not_verified" in duration["conservative_3a_reasons"]
    assert not result["operationally_validated"] and result["operational_durations_accepted"] == 0
    assert all(
        not e["accepted"] and e["status"] == "candidate_crossing" and len(e["support"]) >= 2
        for e in segment["crossings"]
    )
    assert segment["auxiliary_changes"]["trip_id"] == 4
    assert segment["auxiliary_changes"]["start_time"] == 4
    assert duration["waiting_time_s"] is None and duration["walking_time_s"] is None
    assert result == analyze(catalog)


def test_interval_without_justified_point_estimate_has_no_midpoint_fallback(catalog):
    result = analyze(catalog, report(catalog, times=(0, 25, 35, 65, 75)))
    duration = segments(result)[0]["duration"]
    assert duration["status"] == "candidate_interval"
    assert duration["estimated_duration_s"] is None
    assert duration["duration_min_s"] < duration["duration_max_s"]
    assert all(e["estimated_at"] is None for e in segments(result)[0]["crossings"])


def test_qa_accumulated_origin_reversal_keeps_crossing_but_never_a_duration(catalog):
    progress = (100, 150, 141, 132, 123, 114, 105, 150, 400, 475)
    times = (0, 10, 11, 12, 13, 14, 15, 25, 35, 45)
    payload = report(catalog, progress, times)
    assert len(payload["vehicles"][0]["segments"]) == 1
    result = analyze(catalog, payload)
    segment = segments(result)[0]
    assert len(segment["observations"]) == len(progress)
    assert [o["projection"]["progress_m"] for o in segment["observations"]] == pytest.approx(
        progress, abs=0.01
    )
    assert result["summary"]["crossing_candidates"] == 2
    assert result["summary"]["duration_candidates"] == 0
    assert segment["status"] == "indeterminate" and segment["duration"] is None
    assert "origin_recross_or_cumulative_reversal" in segment["reasons"]
    origin = segment["crossings"][0]
    assert origin["earliest_at"] == 1800000000 - 1
    assert origin["latest_at"] == 1800000010 + 1
    assert origin["support"] == segment["observations"][:2]
    audit = segment["endpoint_progression"][0]
    assert audit["ambiguous_for_duration"] and origin["duration_ambiguous"]
    assert len(audit["forward_crossings"]) == 2 and len(audit["returns_before_band"]) == 1
    assert audit["forward_crossings"][0]["support_ids"] == origin["support_ids"]
    assert audit["forward_crossings"][1]["support_ids"] == tuple(
        o["support_id"] for o in segment["observations"][6:8]
    )
    assert audit["returns_before_band"][0]["support_ids"] == tuple(
        o["support_id"] for o in segment["observations"][1:5]
    )
    assert audit["returns_before_band"][0]["cumulative_reverse_m"] == pytest.approx(27, abs=0.01)


def test_small_post_crossing_variations_within_band_keep_candidate_duration(catalog):
    progress = (100, 150, 142, 139, 141, 137, 145, 400, 475)
    times = (0, 10, 11, 12, 13, 14, 15, 25, 35)
    result = analyze(catalog, report(catalog, progress, times))
    segment = segments(result)[0]
    assert result["summary"]["duration_candidates"] == 1
    assert segment["duration"]["status"] == "candidate_interval"
    assert segment["duration"]["duration_min_s"] == pytest.approx(13)
    assert segment["duration"]["duration_max_s"] == pytest.approx(37)
    assert all(
        not a["ambiguous_for_duration"]
        and not a["returns_before_band"]
        and len(a["forward_crossings"]) == 1
        for a in segment["endpoint_progression"]
    )


def test_accumulated_destination_reversal_never_retargets_first_or_last_crossing(catalog):
    progress = (100, 200, 400, 450, 441, 432, 423, 414, 405, 450, 500)
    times = (0, 10, 20, 30, 31, 32, 33, 34, 35, 45, 55)
    result = analyze(catalog, report(catalog, progress, times))
    segment = segments(result)[0]
    assert len(segment["observations"]) == len(progress)
    assert result["summary"]["duration_candidates"] == 0
    assert segment["status"] == "indeterminate" and segment["duration"] is None
    assert segment["reasons"] == ["destination_recross_or_cumulative_reversal"]
    origin, destination = segment["endpoint_progression"]
    assert not origin["ambiguous_for_duration"] and destination["ambiguous_for_duration"]
    assert len(destination["forward_crossings"]) == 2
    assert segment["crossings"][1]["earliest_at"] == 1800000019
    assert segment["crossings"][1]["latest_at"] == 1800000031
    assert segment["crossings"][1]["support"] == segment["observations"][2:4]


def test_return_before_band_is_indeterminate_even_without_later_recross(catalog):
    result = analyze(catalog, report(catalog, (100, 150, 141, 132, 123), (0, 10, 11, 12, 13)))
    segment = segments(result)[0]
    audit = segment["endpoint_progression"][0]
    assert len(audit["forward_crossings"]) == 1 and len(audit["returns_before_band"]) == 1
    assert segment["reasons"] == ["origin_recross_or_cumulative_reversal"]
    assert segment["duration"] is None


@pytest.mark.parametrize(
    "case", ["origin", "destination", "small_variations", "continuous", "interrupted"]
)
def test_summary_counts_match_report_states_and_ambiguous_durations_have_no_numbers(catalog, case):
    cases = {
        "origin": (
            (100, 150, 141, 132, 123, 114, 105, 150, 400, 475),
            (0, 10, 11, 12, 13, 14, 15, 25, 35, 45),
            (),
        ),
        "destination": (
            (100, 200, 400, 450, 441, 432, 423, 414, 405, 450, 500),
            (0, 10, 20, 30, 31, 32, 33, 34, 35, 45, 55),
            (),
        ),
        "small_variations": (
            (100, 150, 142, 139, 141, 137, 145, 400, 475),
            (0, 10, 11, 12, 13, 14, 15, 25, 35),
            (),
        ),
        "continuous": ((0, 200, 300, 500, 600), (0, 20, 30, 50, 60), ()),
        "interrupted": ((0, 200, 250, 300, 500), (0, 20, 25, 30, 50), (2,)),
    }
    progress, times, other = cases[case]
    result = analyze(catalog, report(catalog, progress, times, other_routes=other))
    rows = segments(result)
    assert result["summary"]["duration_candidates"] == sum(
        s["status"] == "candidate_interval" for s in rows
    )
    assert result["summary"]["crossing_candidates"] == sum(
        e["status"] == "candidate_crossing" for s in rows for e in s["crossings"]
    )
    for row in rows:
        if any(a["ambiguous_for_duration"] for a in row["endpoint_progression"]):
            assert row["status"] == "indeterminate" and row["duration"] is None
        if row["duration"] is not None:
            assert row["duration"]["status"] == row["status"]
    if case == "interrupted":
        assert len(rows) == 2 and result["summary"]["duration_candidates"] == 0


@pytest.mark.parametrize(
    "positions,expected", [((0, 100, 200), "DEMO_LINE_A"), ((300, 400, 500), "DEMO_LINE_B")]
)
def test_single_endpoint_cannot_make_duration(catalog, positions, expected):
    result = analyze(catalog, report(catalog, positions, (0, 20, 40)))
    assert result["summary"]["crossing_candidates"] == 1
    assert result["summary"]["duration_candidates"] == 0
    assert segments(result)[0]["duration"] is None
    assert [
        e["stop_id"]
        for e in segments(result)[0]["crossings"]
        if e["status"] == "candidate_crossing"
    ] == [expected]


def test_single_near_stop_observation_is_not_a_crossing(catalog):
    result = analyze(catalog, report(catalog, (135,), (0,)))
    assert result["summary"]["crossing_candidates"] == 0
    assert result["summary"]["duration_candidates"] == 0


def test_never_join_tracker_segments_even_for_same_vehicle(catalog):
    payload = report(catalog, (0, 200, 250, 300, 500), (0, 20, 25, 30, 50), other_routes=(2,))
    result = analyze(catalog, payload)
    assert len(segments(result)) == 2
    assert result["summary"]["crossing_candidates"] == 2
    assert result["summary"]["duration_candidates"] == 0
    assert all(s["duration"] is None for s in segments(result))
    assert "route_change" in {s["tracker_end_reason"] for s in segments(result)}


def test_stricter_crossing_gap_rejects_segment_without_changing_tracker(catalog):
    payload = report(catalog, times=(0, 180, 200, 220, 240))
    assert len(payload["vehicles"][0]["segments"]) == 1  # Tracker permits up to 300 s.
    result = analyze(catalog, payload)
    assert segments(result)[0]["reasons"] == ["observation_gap_excessive"]
    assert result["summary"]["duration_candidates"] == 0


def test_large_uncertainty_is_retained_but_not_an_eligible_duration(catalog):
    result = analyze(catalog, report(catalog, times=(0, 60, 120, 180, 240)))
    segment = segments(result)[0]
    assert segment["duration"]["status"] == "indeterminate"
    assert segment["duration"]["uncertainty_s"] > 85
    assert "duration_uncertainty_too_wide" in segment["reasons"]
    assert result["summary"]["duration_candidates"] == 0


def test_crossing_bracket_cannot_bridge_excessive_near_stop_support_time(catalog):
    payload = report(catalog, (0, 135, 135, 135, 200, 300, 500), (0, 60, 120, 180, 240, 300, 360))
    result = analyze(catalog, payload)
    events = segments(result)[0]["crossings"]
    assert events[0]["status"] == "rejected"
    assert "crossing_support_gap_excessive" in events[0]["reasons"]
    assert result["summary"]["duration_candidates"] == 0


def test_overlapping_endpoint_brackets_cannot_determine_temporal_order(catalog):
    result = analyze(catalog, report(catalog, (0, 600), (0, 30)))
    assert result["summary"]["crossing_candidates"] == 2
    assert "endpoint_crossing_intervals_overlap" in segments(result)[0]["reasons"]
    assert segments(result)[0]["duration"] is None


def test_wrong_direction_and_ambiguous_loop_do_not_make_crossings(catalog):
    result = analyze(catalog, report(catalog, (600, 500, 300, 200, 0), (0, 20, 40, 60, 80)))
    assert "progress_or_reported_sequence_conflict" in segments(result)[0]["reasons"]
    loop = report(catalog, (200, 300, 400), (0, 20, 40), path="loop")
    result = od.analyze(
        loop,
        catalog,
        "DEMO_LOOP",
        pattern(catalog, "loop"),
        "DEMO_LOOP_X",
        "DEMO_LOOP_Y",
        origin_sequence=10,
    )
    assert "ambiguous_shape_branch" in segments(result)[0]["reasons"]
    assert result["summary"]["duration_candidates"] == 0


def test_pattern_must_be_selected_and_cannot_override_tracker_geometry(catalog):
    with pytest.raises(od.InputError, match="PATTERN_REQUIRED"):
        od.select_leg(catalog, "DEMO_LINE", None, "DEMO_LINE_A", "DEMO_LINE_B")
    payload = report(catalog, (500, 600, 800), (0, 20, 40), with_geometry=True)
    result = od.analyze(
        payload, catalog, "DEMO_LINE", pattern(catalog, "branch"), "DEMO_BRANCH_A", "DEMO_BRANCH_B"
    )
    assert "tracker_geometry_pattern_incompatible" in segments(result)[0]["reasons"]


def test_repeated_stops_require_exact_occurrences_and_downstream_order(catalog):
    p = pattern(catalog, "loop")
    with pytest.raises(od.InputError, match="OCCURRENCE"):
        od.select_leg(catalog, "DEMO_LOOP", p, "DEMO_LOOP_X", "DEMO_LOOP_X")
    leg = od.select_leg(catalog, "DEMO_LOOP", p, "DEMO_LOOP_X", "DEMO_LOOP_X", 10, 30)
    assert leg.origin_stop_id == leg.destination_stop_id
    assert (leg.origin_sequence, leg.destination_sequence) == (10, 30)
    with pytest.raises(od.InputError, match="NOT_DOWNSTREAM"):
        od.select_leg(catalog, "DEMO_LOOP", p, "DEMO_LOOP_X", "DEMO_LOOP_X", 30, 10)
    with pytest.raises(od.InputError, match="NOT_IN_PATTERN"):
        od.select_leg(catalog, "DEMO_LOOP", p, "DEMO_LOOP_X", "DEMO_LOOP_Y", 99, 20)


@pytest.mark.parametrize("times", [(0, 0), (20, 0)])
def test_repeated_or_regressing_gps_does_not_fabricate_a_duration(catalog, times):
    positions = (135, 135) if times == (0, 0) else (0, 500)
    result = analyze(catalog, report(catalog, positions, times))
    assert result["summary"]["crossing_candidates"] == 0
    assert result["summary"]["duration_candidates"] == 0


def test_conflicting_static_anchor_templates_are_not_arbitrarily_selected(catalog_path, tmp_path):
    target = tmp_path / "variant.sqlite3"
    shutil.copyfile(catalog_path, target)
    import sqlite3

    connection = sqlite3.connect(target)
    connection.execute(
        "UPDATE stop_times SET shape_distance=999 WHERE trip_pk=(SELECT trip_pk FROM trips WHERE trip_id='DEMO_TRIP_CHANGED') AND sequence=10"
    )
    connection.commit()
    connection.close()
    with Catalog(target) as changed:
        result = analyze(changed)
    assert result["geometry_error"] == "pattern_anchor_template_variants"
    assert result["summary"]["duration_candidates"] == 0


def test_reject_mismatched_catalog_report_route_and_unpinned_inputs(catalog):
    payload = report(catalog)
    with pytest.raises(od.InputError, match="REPORT_ROUTE"):
        od.analyze(payload, catalog, "OTHER", None, "A", "B")
    for metadata in (None, {"sha256": "different"}):
        changed = copy.deepcopy(payload)
        changed["catalog"] = metadata
        with pytest.raises(od.InputError, match="CATALOG"):
            analyze(catalog, changed)


def test_cli_output_is_private_exclusive_deterministic_and_aggregate_only(
    catalog, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr("transmitracker.research.local_pilot.PILOT_ROOT", tmp_path)
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report(catalog)), encoding="utf-8")
    before = path.read_bytes()
    args = [
        str(path),
        "--catalog",
        catalog.connection.execute("PRAGMA database_list").fetchone()[2],
        "--route",
        "DEMO_LINE",
        "--pattern",
        pattern(catalog),
        "--origin",
        "DEMO_LINE_A",
        "--destination",
        "DEMO_LINE_B",
    ]
    for name in ("one.json", "two.json"):
        assert od.main([*args, "--output", str(tmp_path / name)]) == 0
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()
    assert path.read_bytes() == before
    console = capsys.readouterr().out
    assert all(secret not in console for secret in ("DEMO_LINE", "DEMO_VEHICLE", "synthetic://"))
    for output in (tmp_path / "one.json", tmp_path.parent / "escape.json"):
        with pytest.raises(SystemExit) as stopped:
            od.main([*args, "--output", str(output)])
        assert stopped.value.code == 2
