"""Real Tk widgets, isolated by the existing Windows GUI test runner."""

import json
import sqlite3

import pytest

from transmitracker.catalog.schema import SCHEMA_VERSION
from transmitracker.reconstruction.io import snapshot_from_rows
from transmitracker.research.route_tracker import track
from transmitracker.viewer import app as viewer_app
from transmitracker.viewer.app import Viewer
from transmitracker.viewer.demo import make_demo

pytestmark = pytest.mark.gui


def test_manual_selection_timeline_and_canvas_have_only_observed_markers():
    app = Viewer(make_demo())
    failures = []
    app.report_callback_exception = lambda *args: failures.append(args)
    try:
        app.update()
        assert app.winfo_ismapped()
        assert len(app.canvas.find_withtag("geometry")) == 2
        assert len(app.canvas.find_withtag("observed")) == 1
        app.vehicles.selection_set("1")
        app.update()
        assert app.candidate_index == 1
        app.set_cursor(7)
        app.update()
        assert app.cursor == 7
        assert len(app.canvas.find_withtag("observed")) == 8
        assert "Bajo movimiento" in app.details.get("1.0", "end")
        app.select_candidate(0)
        app.set_cursor(6)
        app.update()
        assert len(app.canvas.find_withtag("visual_link")) == 5  # 2 + 3, never across route change
        app.segments.selection_set("0")
        app.update()
        assert app.cursor == 0
        app.select_candidate(2)
        app.set_cursor(7)
        app.update()
        assert not app.canvas.find_withtag("visual_link")
        assert "Ambiguo" in app.details.get("1.0", "end")
        assert "DEMO-S1" in app.details.get("1.0", "end")
        assert "DEMO-S2" in app.details.get("1.0", "end")
        app.fit(False)
        app.magnify(1.25)
        app.update()
        assert app.zoom == 1.25
        assert not failures
    finally:
        app.destroy()


def synthetic_pair(root, name, vehicles, frames, shapes):
    """Two independent catalog versions and tracker reports; all coordinates fictional."""
    route = f"SYNTH-{name}"
    snapshots = [
        snapshot_from_rows(
            source=f"synthetic://{name}",
            endpoint=None,
            catalog_sha256=f"hash-{name}",
            origin="synthetic_fixture",
            received_at=1800000005 + frame * 60,
            rows=[
                dict(
                    vehicle_id=f"{name}-V{i}",
                    route_id=route,
                    latitude=0.01 * i,
                    longitude=0.001 * frame,
                    reported_at=1800000000 + frame * 60,
                )
                for i in range(vehicles)
            ],
        )
        for frame in range(frames)
    ]
    payload = track(snapshots, route)
    payload.update(origins=["synthetic_fixture"], catalog={"sha256": f"hash-{name}"})
    report, catalog = root / f"{name}.json", root / f"{name}.sqlite3"
    report.write_text(json.dumps(payload), encoding="utf-8")
    connection = sqlite3.connect(catalog)
    try:
        connection.executescript(f"""
            PRAGMA user_version={SCHEMA_VERSION};
            CREATE TABLE catalog_versions (sha256,counts_json,timings_json);
            CREATE TABLE patterns (pattern_id,shape_id,route_id);
            CREATE TABLE shape_points (shape_id,latitude,longitude,sequence);
        """)
        connection.execute(
            "INSERT INTO catalog_versions VALUES (?,?,?)", (f"hash-{name}", "{}", "{}")
        )
        for i in range(shapes):
            connection.execute(
                "INSERT INTO patterns VALUES (?,?,?)", (f"{name}-P{i}", f"{name}-S{i}", route)
            )
            connection.executemany(
                "INSERT INTO shape_points VALUES (?,?,?,?)",
                [
                    (f"{name}-S{i}", 0.01 * i, 0.0, 0),
                    (f"{name}-S{i}", 0.01 * i, 0.005, 1),
                ],
            )
        connection.commit()
    finally:
        connection.close()
    return str(report), str(catalog)


@pytest.fixture
def pair_window(tmp_path):
    pairs = {
        "A": synthetic_pair(tmp_path, "A", 2, 4, 2),
        "B": synthetic_pair(tmp_path, "B", 1, 2, 1),
    }
    app = Viewer()
    errors = []
    app.report_callback_exception = lambda *args: errors.append(args)
    try:
        app.load_file(*pairs["A"])
        app.update()
        app.select_candidate(1)
        app.set_cursor(3)
        app.fit(False)
        app.magnify(2)
        app.pan, app.drag_start = (20, 30), (1, 2)
        app.draw()
        app.update()
        yield app, pairs
        assert not errors
    finally:
        app.destroy()


def view_state(app):
    return (
        app.scene,
        app.report_path,
        app.catalog_path,
        app.candidate_index,
        app.segment_index,
        app.cursor,
        app.slider.get(),
        app.slider.cget("to"),
        app.slider.cget("state"),
        app.fit_route,
        app.zoom,
        app.pan,
        app.drag_start,
        app.vehicles.selection(),
        app.segments.selection(),
        tuple(app.vehicles.item(i, "values") for i in app.vehicles.get_children()),
        tuple(app.segments.item(i, "values") for i in app.segments.get_children()),
        app.heading.cget("text"),
        app.time_label.cget("text"),
        app.details.get("1.0", "end"),
        tuple(
            (app.canvas.type(i), tuple(app.canvas.coords(i)), app.canvas.gettags(i))
            for i in app.canvas.find_all()
        ),
    )


def test_switch_catalog_versions_in_same_window_commits_only_valid_pair(pair_window, monkeypatch):
    app, pairs = pair_window
    before = view_state(app)
    original_load = viewer_app.load
    selections = iter(pairs["B"])
    calls = []

    def choose(**kwargs):
        assert view_state(app) == before
        return next(selections)

    def validate(report, catalog):
        assert view_state(app) == before
        calls.append((report, catalog))
        return original_load(report, catalog)

    monkeypatch.setattr(viewer_app.filedialog, "askopenfilename", choose)
    monkeypatch.setattr(viewer_app, "load", validate)
    app.open_pair()
    app.update()
    assert calls == [pairs["B"]]
    assert (app.report_path, app.catalog_path) == pairs["B"]
    assert app.scene.route == "SYNTH-B" and len(app.scene.shapes) == 1
    assert app.candidate_index == 0 and app.segment_index == 0
    assert app.cursor == 0 and app.slider.get() == 0 and app.slider.cget("to") == 1
    assert app.slider.cget("state") == "normal" and app.slider.cget("number_of_steps") == 1
    assert app.fit_route and app.zoom == 1 and app.pan == (0, 0) and app.drag_start is None
    assert app.vehicles.get_children() == ("0",) and app.segments.get_children() == ("0",)
    assert len(app.canvas.find_withtag("geometry")) == 1
    assert len(app.canvas.find_withtag("observed")) == 1
    assert not app.canvas.find_withtag("visual_link")
    assert "1/2" in app.time_label.cget("text")
    assert "B-V0" in app.details.get("1.0", "end") and "A-V1" not in app.details.get("1.0", "end")


@pytest.mark.parametrize("problem", ["wrong_catalog", "missing_file", "invalid_json"])
def test_pair_failure_preserves_previous_scene_and_controls(
    pair_window, monkeypatch, tmp_path, problem
):
    app, pairs = pair_window
    before = view_state(app)
    report, catalog = pairs["B"]
    if problem == "wrong_catalog":
        catalog = pairs["A"][1]
    elif problem == "missing_file":
        report = str(tmp_path / "absent.json")
    else:
        report = str(tmp_path / "invalid.json")
        (tmp_path / "invalid.json").write_text("not JSON", encoding="utf-8")
    selections = iter((report, catalog))
    monkeypatch.setattr(viewer_app.filedialog, "askopenfilename", lambda **kwargs: next(selections))
    app.open_pair()
    app.update()
    assert view_state(app) == before
    assert "Vista anterior conservada" in app.notice.cget("text")
    if problem == "wrong_catalog":
        assert "versión" in app.notice.cget("text")


@pytest.mark.parametrize("cancel_catalog", [False, True])
def test_cancellation_never_loads_or_changes_previous_pair(
    pair_window, monkeypatch, cancel_catalog
):
    app, pairs = pair_window
    before, notice = view_state(app), app.notice.cget("text")
    selections = iter((pairs["B"][0], "") if cancel_catalog else ("",))
    monkeypatch.setattr(viewer_app.filedialog, "askopenfilename", lambda **kwargs: next(selections))
    monkeypatch.setattr(
        viewer_app, "load", lambda *args: pytest.fail("Cancelled pair must not load")
    )
    app.open_pair()
    app.update()
    assert view_state(app) == before and app.notice.cget("text") == notice


def test_existing_report_only_flow_still_works(tmp_path, monkeypatch):
    report, _ = synthetic_pair(tmp_path, "B", 1, 2, 1)
    app = Viewer()
    errors = []
    app.report_callback_exception = lambda *args: errors.append(args)
    try:
        monkeypatch.setattr(viewer_app.filedialog, "askopenfilename", lambda **kwargs: report)
        app.open_report()
        app.update()
        assert app.report_path == report and app.catalog_path is None
        assert app.scene.route == "SYNTH-B" and not app.scene.shapes
        assert not app.canvas.find_withtag("geometry") and not errors
    finally:
        app.destroy()


@pytest.mark.parametrize("empty", ["candidates", "observations"])
def test_session_reset_clears_temporal_state_when_new_scene_is_empty(
    pair_window, monkeypatch, empty
):
    app, pairs = pair_window
    report, catalog = pairs["B"]
    with open(report, encoding="utf-8") as source:
        payload = json.load(source)
    if empty == "candidates":
        payload["vehicles"] = []
    else:
        payload["vehicles"][0]["all_source_vehicle_sightings"] = []
        payload["vehicles"][0]["segments"] = []
    with open(report, "w", encoding="utf-8") as output:
        json.dump(payload, output)
    selections = iter((report, catalog))
    monkeypatch.setattr(viewer_app.filedialog, "askopenfilename", lambda **kwargs: next(selections))
    app.open_pair()
    app.update()
    assert app.scene.route == "SYNTH-B" and app.cursor == 0 and app.slider.get() == 0
    assert app.slider.cget("state") == "disabled" and app.slider.cget("to") == 1
    assert not app.segments.get_children() and not app.canvas.find_withtag("observed")
    assert app.zoom == 1 and app.pan == (0, 0) and app.fit_route
