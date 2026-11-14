import json
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest

from transmitracker.catalog import CatalogError
from transmitracker.gtfs import FeedError
from transmitracker.reconstruction.geometry import MeasuredShape
from transmitracker.reconstruction.io import snapshot_from_rows
from transmitracker.research import route_tracker as tracker


def frame(time, rows=None):
    rows = (
        rows
        if rows is not None
        else [
            dict(
                vehicle_id="DEMO_A",
                route_id="DEMO_R",
                latitude=4.65,
                longitude=-74.1 + time * 0.00001,
                reported_at=1800000000 + time,
                start_time=str(time),
                trip_id="NO_MATCH",
            )
        ]
    )
    return snapshot_from_rows(
        source="synthetic://route",
        endpoint=None,
        catalog_sha256="synthetic",
        origin="synthetic_fixture",
        rows=rows,
        feed_as_of=1800000000 + time,
        received_at=1800000005 + time,
    )


def row(time, **changes):
    return {**json.loads(frame(time).observations[0].raw_json), **changes}


def segments(report):
    return [s for v in report["vehicles"] for s in v["segments"]]


def reasons(report):
    return {i["reason"] for v in report["vehicles"] for i in v["incidents"]}


def test_grouping_multiple_routes_sources_and_auxiliary_changes():
    snapshots = [
        frame(
            t,
            [
                row(t),
                row(t, vehicle_id="DEMO_B"),
                row(t, vehicle_id="DEMO_OTHER", route_id="OTHER"),
            ],
        )
        for t in (0, 60, 120)
    ]
    report = tracker.track(snapshots, "DEMO_R")
    assert report["vehicle_candidates"] == 2
    assert report["original_route_observations"] == 6
    assert report["distinct_published_gps_times"] == 6
    assert {s["state"] for s in segments(report)} == {"movimiento_candidato"}
    assert report["vehicles"][0]["auxiliary_changes"]["start_time"] == 2
    assert report == tracker.track(snapshots, "DEMO_R")
    assert not report["operationally_verified"] and report["network_requests"] == 0
    second = replace(snapshots[0], source="synthetic://another")
    # Namespace is observation source; use an independent well-formed second feed.
    second = snapshot_from_rows(
        source=second.source,
        endpoint=None,
        catalog_sha256="synthetic",
        origin="synthetic_fixture",
        rows=[row(0)],
        received_at=1800000005,
    )
    assert tracker.track([snapshots[0], second], "DEMO_R")["vehicle_candidates"] == 3


def test_duplicates_same_time_conflicts_and_untrusted_ids():
    report = tracker.track([frame(0), frame(0), frame(60)], "DEMO_R")
    assert len(segments(report)[0]["fixes"]) == 2
    assert report["vehicles"][0]["duplicates_removed_from_movement"] == 1
    conflict = tracker.track([frame(0), frame(0, [row(0, longitude=-74.11)]), frame(60)], "DEMO_R")
    assert "conflicting_positions_at_same_gps_time" in reasons(conflict)
    assert not any(s["activity_candidate"] == "movimiento_candidato" for s in segments(conflict))
    missing = tracker.track([frame(0, [row(0, vehicle_id=None)])], "DEMO_R")
    assert missing["observations_without_vehicle_id"] == 1
    assert missing["vehicle_candidates"] == 0


@pytest.mark.parametrize(
    "middle,expected",
    [
        ([row(90, route_id="OTHER")], "route_change"),
        ([], "missing_from_complete_snapshot"),
        ([row(90, reported_at=1800000030)], "gps_time_regression"),
        ([row(90, longitude=-73.0)], "implausible_spatial_jump"),
    ],
)
def test_discontinuity_never_bridged(middle, expected):
    report = tracker.track(
        [frame(0), frame(60), frame(90, middle), frame(120), frame(180)], "DEMO_R"
    )
    assert expected in reasons(report)
    for segment in segments(report):
        times = [f["observation"]["reported_at"] for f in segment["fixes"]]
        assert times == sorted(set(times))
        assert not (1800000060 in times and 1800000120 in times)


def test_gap_stationary_and_stale():
    gap = tracker.track([frame(0), frame(60), frame(500)], "DEMO_R")
    assert "gps_gap" in reasons(gap)
    stationary = tracker.track(
        [frame(t, [row(t, longitude=-74.1)]) for t in (0, 60, 120)], "DEMO_R"
    )
    assert segments(stationary)[0]["state"] == "estacionario"
    stale = tracker.track([frame(600, [row(0)])], "DEMO_R")
    assert "stale_or_future_gps" in reasons(stale)


class Geometry:
    def __init__(self, *, offset=0, ambiguous=False):
        self.offset, self.ambiguous = offset, ambiguous

    def project(self, obs):
        if self.ambiguous:
            return [], None, "ambiguous_geometry"
        p = {
            "shape_id": "DEMO_SHAPE",
            "pattern_ids": ["DEMO_P1", "DEMO_P2"],
            "projection": {
                "progress_m": (obs.longitude + 74.1) * 100000 + self.offset,
                "residual_m": 1,
                "edge_index": 0,
            },
        }
        return [p], p, None


def test_geometry_progress_and_shared_patterns_remain_ambiguous():
    report = tracker.track([frame(t) for t in (0, 60, 120)], "DEMO_R", geometry=Geometry())
    segment = segments(report)[0]
    assert segment["state"] == "movimiento_candidato"
    assert segment["geometric_progress_m"] > 0
    assert segment["pattern_ambiguous"]
    assert segment["fixes"][0]["selected_geometry"]["pattern_ids"] == ["DEMO_P1", "DEMO_P2"]
    ambiguous = tracker.track([frame(0), frame(60)], "DEMO_R", geometry=Geometry(ambiguous=True))
    assert {s["state"] for s in segments(ambiguous)} == {"ambiguo"}


def test_geometry_backtrack_is_a_cut():
    snapshots = [frame(0), frame(60), frame(120, [row(120, longitude=-74.0998)])]
    report = tracker.track(snapshots, "DEMO_R", geometry=Geometry())
    assert "geometry_backtrack" in reasons(report)
    assert len(segments(report)) == 2


def test_route_geometry_uses_existing_projection_and_keeps_patterns():
    class Connection:
        def execute(self, sql, params):
            if "FROM patterns" in sql:
                return [
                    {"pattern_id": "P1", "shape_id": "S"},
                    {"pattern_id": "P2", "shape_id": "S"},
                ]

            class Rows(list):
                def fetchall(self):
                    return self

            return Rows([(4.65, -74.1), (4.65, -74.09)])

    class Catalog:
        connection = Connection()

    geometry = tracker.RouteGeometry(Catalog(), "DEMO_R", tracker.Parameters())
    assert isinstance(geometry.shapes["S"].shape, MeasuredShape)
    candidates, selected, error = geometry.project(frame(60).observations[0])
    assert error is None and selected["pattern_ids"] == ["P1", "P2"]
    assert len(candidates) == 1


def test_two_distinct_viable_shapes_never_select_one_arbitrarily():
    with sqlite3.connect(":memory:") as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE patterns (pattern_id, shape_id, route_id)")
        connection.execute("CREATE TABLE shape_points (shape_id, latitude, longitude, sequence)")
        connection.executemany(
            "INSERT INTO patterns VALUES (?,?,?)",
            [("P1", "S1", "DEMO_R"), ("P2", "S2", "DEMO_R")],
        )
        connection.executemany(
            "INSERT INTO shape_points VALUES (?,?,?,?)",
            [
                ("S1", 4.65, -74.1, 1),
                ("S1", 4.65, -74.09, 2),
                ("S2", 4.6502, -74.1, 1),
                ("S2", 4.6502, -74.09, 2),
            ],
        )
        geometry = tracker.RouteGeometry(
            SimpleNamespace(connection=connection), "DEMO_R", tracker.Parameters()
        )
        candidates, selected, error = geometry.project(frame(60).observations[0])
        assert {c["shape_id"] for c in candidates} == {"S1", "S2"}
        assert all(c["projection"] is not None for c in candidates)
        assert selected is None and error == "ambiguous_geometry"
        report = tracker.track([frame(0), frame(60)], "DEMO_R", geometry=geometry)
        assert {s["state"] for s in segments(report)} == {"ambiguo"}
        assert all(f["selected_geometry"] is None for s in segments(report) for f in s["fixes"])


def test_duplicate_after_absence_does_not_reseed_movement():
    report = tracker.track(
        [frame(0), frame(60), frame(90, []), frame(120, [row(60)]), frame(180)], "DEMO_R"
    )
    assert "missing_from_complete_snapshot" in reasons(report)
    assert report["vehicles"][0]["duplicates_removed_from_movement"] == 1
    assert len(segments(report)[-1]["fixes"]) == 1


def test_exact_route_selection_and_raw_provenance_preserved():
    snapshots = [frame(0), frame(60)]
    report = tracker.track(snapshots, "DEMO_R")
    assert (
        report["original_route_sightings"][0]["observation"]["raw_json"]
        == snapshots[0].observations[0].raw_json
    )
    assert report["original_route_sightings"][0]["snapshot_id"] == snapshots[0].snapshot_id
    assert tracker.track(snapshots, "demo_r")["vehicle_candidates"] == 0


def test_cli_private_output_and_pb_integrity(tmp_path, monkeypatch):
    from transmitracker.research.local_pilot import make_fixture

    directory = tmp_path / "session"
    make_fixture(directory)
    monkeypatch.setattr(tracker, "project_path", lambda p: __import__("pathlib").Path(p).resolve())
    monkeypatch.setattr("transmitracker.research.local_pilot.PILOT_ROOT", tmp_path)
    for output in (tmp_path / "one.json", tmp_path / "two.json"):
        assert tracker.main([str(directory), "--route", "DEMO_ROUTE", "--output", str(output)]) == 0
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()
    with pytest.raises(SystemExit):
        tracker.main(
            [
                str(directory),
                "--route",
                "DEMO_ROUTE",
                "--output",
                str(tmp_path.parent / "public.json"),
            ]
        )
    (directory / "capture_00.pb").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="hash"):
        tracker.run(directory, "DEMO_ROUTE")


@pytest.mark.parametrize(
    "error,code",
    [
        (FileNotFoundError("PRIVATE_ID"), "INPUT_MISSING"),
        (PermissionError("PRIVATE_ID"), "INPUT_READ"),
        (json.JSONDecodeError("PRIVATE_ID", "PRIVATE_ID", 0), "INPUT_JSON"),
        (UnicodeDecodeError("utf-8", b"PRIVATE_ID", 0, 1, "private"), "INPUT_ENCODING"),
        (CatalogError("PRIVATE_ID"), "CATALOG"),
        (sqlite3.DatabaseError("PRIVATE_ID"), "CATALOG"),
        (ValueError("Saved capture hash mismatch"), "INPUT_INTEGRITY"),
        (FeedError("Invalid coordinates PRIVATE_ID 4.650001 -74.100001"), "INPUT_INVALID"),
        (KeyError("PRIVATE_ID"), "INPUT_INVALID"),
        (TypeError("PRIVATE_ID"), "INPUT_INVALID"),
    ],
)
def test_cli_distinguishes_input_errors_without_private_details(
    tmp_path, monkeypatch, capsys, error, code
):
    monkeypatch.setattr("transmitracker.research.local_pilot.PILOT_ROOT", tmp_path)

    def reject(*args):
        raise error

    monkeypatch.setattr(tracker, "run", reject)
    with pytest.raises(SystemExit) as stopped:
        tracker.main(
            [str(tmp_path), "--route", "PRIVATE_ID", "--output", str(tmp_path / "out.json")]
        )
    assert stopped.value.code == 2
    output = capsys.readouterr()
    assert not output.out and f"[{code}]" in output.err
    assert all(secret not in output.err for secret in ("PRIVATE_ID", "4.650001", "-74.100001"))
    assert not (tmp_path / "out.json").exists()


def test_cli_output_errors_are_distinct_and_do_not_overwrite(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("transmitracker.research.local_pilot.PILOT_ROOT", tmp_path)
    calls = []
    monkeypatch.setattr(tracker, "run", lambda *args: calls.append(args) or {})
    output = tmp_path / "out.json"
    output.write_text("unchanged", encoding="utf-8")
    for path, code in ((output, "OUTPUT_EXISTS"), (tmp_path.parent / "public.json", "OUTPUT_PATH")):
        with pytest.raises(SystemExit) as stopped:
            tracker.main([str(tmp_path), "--route", "PRIVATE_ID", "--output", str(path)])
        assert stopped.value.code == 2
        assert f"[{code}]" in capsys.readouterr().err
    assert not calls and output.read_text(encoding="utf-8") == "unchanged"

    def denied(*args):
        raise PermissionError("PRIVATE_ID 4.650001 -74.100001")

    monkeypatch.setattr(tracker, "write_json", denied)
    with pytest.raises(SystemExit) as stopped:
        tracker.main(
            [str(tmp_path), "--route", "PRIVATE_ID", "--output", str(tmp_path / "new.json")]
        )
    assert stopped.value.code == 2
    message = capsys.readouterr().err
    assert "[OUTPUT_WRITE]" in message and "PRIVATE_ID" not in message and "4.650001" not in message
