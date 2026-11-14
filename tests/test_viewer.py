"""Offline preparation and catalog contracts, without a graphical runtime."""

import copy
import json
import sqlite3

import pytest

from transmitracker.viewer.data import Transform, ViewerError, load, prepare
from transmitracker.viewer.demo import demo_report, make_demo


def test_demo_states_candidates_and_segment_selection_are_preserved():
    scene = make_demo()
    assert scene.synthetic and len(scene.candidates) == 3 and len(scene.shapes) == 2
    first = scene.candidate(0)
    assert {s.state for s in first.segments} == {"interrumpido", "movimiento_candidato"}
    assert first.segments[0].end == "route_change"
    assert first.segment_at(first.fixes[0]) == first.segments[0]
    assert all(s.pattern_ambiguous for s in first.segments)
    assert {s.state for s in scene.candidate(1).segments} == {"estacionario"}
    ambiguous = scene.candidate(2)
    assert {s.state for s in ambiguous.segments} == {"ambiguo"}
    assert all(not s.shapes and len(s.alternatives) == 2 for s in ambiguous.segments)
    assert scene.shapes[0].patterns == ("DEMO-P1", "DEMO-P2")
    for index in (-1, 3, "DEMO-A"):
        with pytest.raises(ViewerError):
            scene.candidate(index)


@pytest.mark.parametrize(
    "problem",
    [
        "algorithm",
        "verified",
        "missing",
        "state",
        "duplicate",
        "foreign",
        "membership",
        "metrics",
        "catalog",
    ],
)
def test_invalid_report_rejected_without_payload_details(problem):
    payload, _ = demo_report()
    if problem == "algorithm":
        payload["algorithm"] = "PRIVATE_ID"
    elif problem == "verified":
        payload["operationally_verified"] = True
    elif problem == "missing":
        del payload["vehicles"][0]["segments"]
    elif problem == "state":
        payload["vehicles"][0]["segments"][0]["state"] = "PRIVATE_ID"
    elif problem == "duplicate":
        payload["vehicles"].append(payload["vehicles"][0])
    elif problem == "foreign":
        payload["vehicles"][0]["segments"][0]["fixes"][0]["observation"]["route_id"] = "PRIVATE_ID"
    elif problem == "membership":
        payload["vehicles"][0]["segments"][0]["fixes"][0] = copy.deepcopy(
            payload["vehicles"][0]["segments"][0]["fixes"][0]
        )
        payload["vehicles"][0]["segments"][0]["fixes"][0]["observation"]["longitude"] += 0.01
    elif problem == "catalog":
        payload["catalog"] = "PRIVATE_ID"
    else:
        payload["vehicles"][0]["segments"][0]["sampled_distance_m"] = "PRIVATE_ID"
    with pytest.raises(ViewerError) as error:
        prepare(payload)
    assert "PRIVATE_ID" not in str(error.value)


def test_absent_and_non_observed_coordinates_are_not_drawable():
    payload, _ = demo_report()
    for f in payload["vehicles"][0]["all_source_vehicle_sightings"]:
        f["observation"]["position_kind"] = "extrapolated"
    for segment in payload["vehicles"][0]["segments"]:
        for f in segment["fixes"]:
            f["observation"]["position_kind"] = "extrapolated"
    scene = prepare(payload)
    assert all(f.point is None for f in scene.candidate(0).fixes)


def test_repeated_gps_and_capture_order_do_not_create_new_segments():
    payload, _ = demo_report()
    vehicle = payload["vehicles"][0]
    original = copy.deepcopy(vehicle["all_source_vehicle_sightings"][0])
    original["snapshot_index"] = 99
    vehicle["all_source_vehicle_sightings"].append(original)
    scene = prepare(payload)
    candidate = scene.candidate(0)
    assert candidate.fixes[-1].timestamp == candidate.fixes[0].timestamp
    assert candidate.segment_at(candidate.fixes[-1]) is None
    assert len(candidate.segments) == 2


def test_transform_preserves_aspect_direction_and_degenerate_bounds():
    transform = Transform.fit([(0.0, 0.0), (0.01, 0.01)], 600, 600)
    a, b = transform.point((0.0, 0.0)), transform.point((0.01, 0.01))
    assert b[0] > a[0] and b[1] < a[1]
    assert b[0] - a[0] == pytest.approx(a[1] - b[1], rel=1e-6)
    assert Transform.fit([(0.0, 0.0)], 600, 600).point((0.0, 0.0)) == (300, 300)
    assert transform.point((0.005, 0.005), pan=(10, 20)) == pytest.approx((310, 320))


def test_load_catalog_read_only_version_and_missing_shapes(tmp_path):
    from transmitracker.catalog.schema import SCHEMA_VERSION

    report, _ = demo_report()
    report["catalog"] = {"sha256": "synthetic-hash"}
    path, db = tmp_path / "report.json", tmp_path / "catalog.sqlite3"
    path.write_text(json.dumps(report), encoding="utf-8")
    connection = sqlite3.connect(db)
    connection.executescript(f"""
        PRAGMA user_version={SCHEMA_VERSION};
        CREATE TABLE catalog_versions (sha256,counts_json,timings_json);
        INSERT INTO catalog_versions VALUES ('synthetic-hash','{{}}','{{}}');
        CREATE TABLE patterns (pattern_id,shape_id,route_id);
        CREATE TABLE shape_points (shape_id,latitude,longitude,sequence);
        INSERT INTO patterns VALUES ('P1','S1','DEMO-R'),('P2','S1','DEMO-R'),('P3','S2','DEMO-R');
        INSERT INTO shape_points VALUES ('S1',0,0,0),('S1',0,.01,1),('S2',.0001,0,0),('S2',.0001,.01,1);
    """)
    connection.close()
    before = db.read_bytes()
    scene = load(path, db)
    assert len(scene.shapes) == 2 and scene.shapes[0].patterns == ("P1", "P2")
    assert db.read_bytes() == before
    report["catalog"]["sha256"] = "different"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ViewerError, match="versión"):
        load(path, db)
    with pytest.raises(ViewerError):
        load(path, tmp_path / "absent.sqlite3")
    assert not (tmp_path / "absent.sqlite3").exists()
    path.write_text("not JSON PRIVATE_ID", encoding="utf-8")
    with pytest.raises(ViewerError) as error:
        load(path)
    assert "PRIVATE_ID" not in str(error.value)


def test_empty_report_is_explorable():
    report, _ = demo_report()
    report["vehicles"] = []
    assert not prepare(report).candidates


def test_report_with_regressing_gps_inside_segment_is_invalid():
    payload, _ = demo_report()
    # The segment and its original agree, but their temporal relation is invalid.
    payload["vehicles"][0]["segments"][0]["fixes"][1]["observation"]["reported_at"] = 1
    with pytest.raises(ViewerError):
        prepare(payload)


def test_cli_rejects_unreadable_report_without_opening_window(tmp_path, capsys):
    from transmitracker.viewer.__main__ import main

    with pytest.raises(SystemExit) as stopped:
        main([str(tmp_path / "PRIVATE_ID.json")])
    assert stopped.value.code == 2
    assert "PRIVATE_ID" not in capsys.readouterr().err
