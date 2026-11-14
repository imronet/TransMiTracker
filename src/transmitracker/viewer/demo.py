"""Fictional equatorial coordinates, generated in memory with the unchanged tracker."""

import sqlite3
from types import SimpleNamespace

from transmitracker.reconstruction.io import snapshot_from_rows
from transmitracker.research.route_tracker import Parameters, RouteGeometry, track
from transmitracker.viewer.data import Shape, prepare


def demo_report():
    source = "synthetic://viewer"
    shapes = (
        Shape("DEMO-S1", ("DEMO-P1", "DEMO-P2"), ((0.0, 0.0), (0.0, 0.02))),
        Shape("DEMO-S2", ("DEMO-P3",), ((0.0002, 0.014), (0.0002, 0.02))),
    )
    snapshots = []
    for i in range(8):
        timestamp = 1800000000 + i * 60
        rows = [
            {
                "vehicle_id": "DEMO-A",
                "route_id": "DEMO-OTHER" if i == 3 else "DEMO-R",
                "latitude": 0.0,
                "longitude": min(i, 5) * 0.001,
                "reported_at": timestamp,
            },
            {
                "vehicle_id": "DEMO-B",
                "route_id": "DEMO-R",
                "latitude": 0.0,
                "longitude": 0.007,
                "reported_at": timestamp,
            },
            {
                "vehicle_id": "DEMO-C",
                "route_id": "DEMO-R",
                "latitude": 0.0001,
                "longitude": 0.015,
                "reported_at": timestamp,
            },
        ]
        snapshots.append(
            snapshot_from_rows(
                source=source,
                endpoint=None,
                catalog_sha256="synthetic",
                origin="synthetic_fixture",
                rows=rows,
                received_at=timestamp + 5,
                feed_as_of=timestamp + 2,
            )
        )
    connection = sqlite3.connect(":memory:")
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE patterns (pattern_id,shape_id,route_id)")
        connection.execute("CREATE TABLE shape_points (shape_id,latitude,longitude,sequence)")
        for shape in shapes:
            connection.executemany(
                "INSERT INTO patterns VALUES (?,?,?)",
                [(p, shape.identity, "DEMO-R") for p in shape.patterns],
            )
            connection.executemany(
                "INSERT INTO shape_points VALUES (?,?,?,?)",
                [(shape.identity, *point, i) for i, point in enumerate(shape.points)],
            )
        report = track(
            snapshots,
            "DEMO-R",
            geometry=RouteGeometry(
                SimpleNamespace(connection=connection), "DEMO-R", Parameters(max_gap_s=300)
            ),
        )
        report.update(origins=["synthetic_fixture"], catalog=None)
    finally:
        connection.close()
    return report, shapes


def make_demo():
    report, shapes = demo_report()
    return prepare(
        report,
        shapes,
        "DEMOSTRACIÓN SINTÉTICA · coordenadas ficticias · dos geometrías, sin servicio elegido",
    )
