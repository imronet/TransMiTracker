"""Offline catalog scenarios; every row below is synthetic, never official data."""

import csv
import io
from datetime import date, datetime
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from transmitracker.catalog import CatalogError
from transmitracker.catalog.__main__ import main
from transmitracker.catalog.common import file_hash, gtfs_seconds
from transmitracker.catalog.importer import import_catalog
from transmitracker.catalog.queries import Catalog


def when(value="2026-11-09T07:59:00-05:00"):
    return datetime.fromisoformat(value)


def write_zip(path, tables):
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, (columns, records) in tables.items():
            stream = io.StringIO(newline="")
            writer = csv.writer(stream)
            writer.writerow(columns)
            writer.writerows(records)
            archive.writestr(name, stream.getvalue().encode("utf-8"))
    return path


def make_catalog_tables():
    routes = [[f"{i:03}", f"SYN{i}", f"Ruta sintetica {i}", 3] for i in range(1, 10)]
    stops = [
        ["STN", "EST", "Estación Central", "1", "", ""],
        ["0001", "A001", "Plataforma Á Norte", "0", "STN", "A"],
        ["0002", "B001", "Plataforma B Sur", "0", "STN", "B"],
        ["0003", "MID", "Intermedia", "0", "", ""],
        ["0004", "FIN", "Destino final", "0", "", ""],
        ["0005", "BR", "Variante ramal", "0", "", ""],
        ["0006", "PRE", "Parada anterior", "0", "", ""],
    ]
    trips, times = [], []

    def trip(identity, route, direction, service, sequence, shape="SH1"):
        trips.append([identity, route, service, direction, shape])
        for order, (stop, clock, pickup, drop) in enumerate(sequence, 1):
            times.append([identity, order * 10, stop, clock, clock, pickup, drop])

    trip(
        "MAIN",
        "001",
        0,
        "WK",
        [
            ("0006", "07:50:00", 0, 0),
            ("0001", "08:00:00", 0, 0),
            ("0003", "08:10:00", 0, 0),
            ("0004", "08:20:00", 0, 0),
        ],
    )
    trip(
        "BRANCH",
        "001",
        0,
        "WK",
        [("0001", "08:05:00", 0, 0), ("0005", "08:15:00", 0, 0), ("0004", "08:25:00", 0, 0)],
        "SH2",
    )
    trip(
        "REVERSE",
        "001",
        1,
        "WK",
        [
            ("0004", "08:00:00", 0, 0),
            ("0003", "08:10:00", 0, 0),
            ("0002", "08:20:00", 0, 0),
            ("0006", "08:30:00", 0, 0),
        ],
    )
    trip("SPECIAL", "002", 0, "EX", [("0001", "08:00:00", 0, 0), ("0004", "08:10:00", 0, 0)])
    trip("NIGHT", "001", 0, "WK", [("0001", "25:00:00", 0, 0), ("0004", "25:10:00", 0, 0)])
    trip("NIGHT49", "001", 0, "WK", [("0001", "49:00:00", 0, 0), ("0004", "49:10:00", 0, 0)])
    trip("NO_PICKUP", "003", 0, "WK", [("0001", "08:00:00", 1, 0), ("0004", "08:10:00", 0, 0)])
    trip("CONDITIONAL", "004", 0, "WK", [("0001", "08:00:00", 2, 0), ("0005", "08:10:00", 0, 3)])
    trip("UNKNOWN", "005", "", "WK", [("0001", "08:00:00", 0, 0), ("0005", "08:10:00", 0, 0)])
    trip(
        "LOOP",
        "006",
        0,
        "WK",
        [
            ("0001", "08:00:00", 0, 0),
            ("0003", "08:10:00", 0, 0),
            ("0001", "08:20:00", 0, 0),
            ("0004", "08:30:00", 0, 0),
        ],
    )
    trip("NO_DROPOFF", "007", 0, "WK", [("0001", "08:00:00", 0, 0), ("0004", "08:10:00", 0, 1)])
    trip("FREQ_APPROX", "008", 0, "WK", [("0001", "00:00:00", 0, 0), ("0004", "00:10:00", 0, 0)])
    trip("FREQ_EXACT", "009", 0, "WK", [("0001", "00:00:00", 0, 0), ("0004", "00:10:00", 0, 0)])
    return {
        "agency.txt": (
            ["agency_name", "agency_timezone"],
            [["Synthetic agency", "America/Bogota"]],
        ),
        "routes.txt": (["route_id", "route_short_name", "route_long_name", "route_type"], routes),
        "stops.txt": (
            [
                "stop_id",
                "stop_code",
                "stop_name",
                "location_type",
                "parent_station",
                "platform_code",
            ],
            stops,
        ),
        "trips.txt": (["trip_id", "route_id", "service_id", "direction_id", "shape_id"], trips),
        "stop_times.txt": (
            [
                "trip_id",
                "stop_sequence",
                "stop_id",
                "arrival_time",
                "departure_time",
                "pickup_type",
                "drop_off_type",
            ],
            times,
        ),
        "shapes.txt": (
            ["shape_id", "shape_pt_sequence", "shape_pt_lat", "shape_pt_lon"],
            [["SH1", 1, 4.65, -74.06], ["SH2", 1, 4.66, -74.05]],
        ),
        "calendar.txt": (
            [
                "service_id",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
                "start_date",
                "end_date",
            ],
            [["WK", 1, 1, 1, 1, 1, 0, 0, "20260101", "20261231"]],
        ),
        "calendar_dates.txt": (
            ["service_id", "date", "exception_type"],
            [["WK", "20261112", 2], ["EX", "20261112", 1]],
        ),
        "frequencies.txt": (
            ["trip_id", "start_time", "end_time", "headway_secs", "exact_times"],
            [
                ["FREQ_EXACT", "05:00:00", "09:00:00", 600, 1],
                ["FREQ_APPROX", "23:50:00", "25:30:00", 600, 0],
            ],
        ),
    }


@pytest.fixture
def catalog_tables():
    return make_catalog_tables()


@pytest.fixture(scope="module")
def catalog_path(tmp_path_factory):
    tmp_path = tmp_path_factory.mktemp("static_catalog")
    archive = write_zip(tmp_path / "synthetic.zip", make_catalog_tables())
    database = tmp_path / "catalog.sqlite3"
    import_catalog(
        archive, database, source_url="https://example.invalid/synthetic.zip", batch_size=2
    )
    return database


def main_pattern(catalog):
    return next(
        option
        for option in catalog.options("0001", when())
        if option["route_id"] == "001"
        and catalog.connection.execute(
            "SELECT 1 FROM pattern_stops WHERE pattern_id=? AND stop_id='0003'",
            (option["pattern_id"],),
        ).fetchone()
    )


def test_catalog_metadata_ids_and_indexes(catalog_path):
    with Catalog(catalog_path) as catalog:
        info = catalog.info()
        assert info["counts"]["trips"] == 13
        assert info["source_url"].endswith("synthetic.zip")
        assert "idx_stop_times_stop_departure" in info["indexes"]
        assert catalog.connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            catalog.connection.execute(
                "SELECT typeof(route_id) FROM routes WHERE route_id='001'"
            ).fetchone()[0]
            == "text"
        )


@pytest.mark.parametrize(
    "query,expected",
    [("estacion", "STN"), ("plataforma a", "0001"), ("A001", "0001"), ("destino", "0004")],
)
def test_search_name_code_and_accents(catalog_path, query, expected):
    with Catalog(catalog_path) as catalog:
        assert expected in {row["stop_id"] for row in catalog.search_stops(query)}


def test_station_expands_platforms_but_platform_does_not_expand_siblings(catalog_path):
    with Catalog(catalog_path) as catalog:
        assert set(catalog.stop_family("STN")) == {"STN", "0001", "0002"}
        assert catalog.stop_family("0001") == ["0001"]
        assert {
            o["direction_id"] for o in catalog.options("STN", when()) if o["route_id"] == "001"
        } == {0, 1}
        assert {
            o["direction_id"] for o in catalog.options("0001", when()) if o["route_id"] == "001"
        } == {0}


def test_routes_and_patterns_are_distinct(catalog_path):
    with Catalog(catalog_path) as catalog:
        options = [o for o in catalog.options("0001", when()) if o["route_id"] == "001"]
        assert len({o["pattern_id"] for o in options}) == 2
        assert "001" in {r["route_id"] for r in catalog.routes_for_stop("0001", when())}


def test_only_downstream_destinations(catalog_path):
    with Catalog(catalog_path) as catalog:
        option = main_pattern(catalog)
        result = catalog.destinations("0001", "001", 0, option["pattern_id"], when())
        assert [row["stop_id"] for row in result] == ["0003", "0004"]
        assert result[0]["arrival_at"] == "2026-11-09T08:10:00-05:00"
        assert (
            catalog.validate_destination("0001", "001", 0, option["pattern_id"], when(), "0004")[
                "sequence"
            ]
            == 40
        )
        for forbidden in ("0006", "0005", "0002"):
            with pytest.raises(CatalogError, match="downstream"):
                catalog.validate_destination(
                    "0001", "001", 0, option["pattern_id"], when(), forbidden
                )


@pytest.mark.parametrize("route,direction", [("001", 1), ("002", 0), ("001", None)])
def test_rejects_wrong_route_direction_pattern(catalog_path, route, direction):
    with Catalog(catalog_path) as catalog:
        option = main_pattern(catalog)
        with pytest.raises(CatalogError, match="incompatible"):
            catalog.destinations("0001", route, direction, option["pattern_id"], when())


def test_calendar_exceptions_and_bounds(catalog_path):
    with Catalog(catalog_path) as catalog:
        assert catalog.active_services(date(2026, 11, 12)) == {"EX"}
        assert catalog.active_services(date(2026, 11, 14)) == set()
        assert catalog.active_services(date(2027, 1, 4)) == set()
        options = catalog.options("0001", when("2026-11-12T07:59:00-05:00"))
        assert {row["route_id"] for row in options} == {"002"}


def test_after_midnight_uses_previous_service_day(catalog_path):
    with Catalog(catalog_path) as catalog:
        options = catalog.options("0001", when("2026-11-14T00:59:00-05:00"), window_minutes=20)
        option = next(o for o in options if o["route_id"] == "001")
        assert "2026-11-13" in option["service_dates"]
        destinations = catalog.destinations(
            "0001",
            "001",
            0,
            option["pattern_id"],
            when("2026-11-14T00:59:00-05:00"),
            window_minutes=20,
        )
        assert destinations[0]["arrival_at"] == "2026-11-14T01:10:00-05:00"


def test_times_over_48_hours(catalog_path):
    with Catalog(catalog_path) as catalog:
        options = catalog.options("0001", when("2026-11-11T00:59:00-05:00"), window_minutes=20)
        assert any("2026-11-09" in o["service_dates"] for o in options if o["route_id"] == "001")


def test_frequency_exact_and_approximate_do_not_invent_times(catalog_path):
    with Catalog(catalog_path) as catalog:
        exact = next(
            o
            for o in catalog.options("0001", when("2026-11-09T08:03:00-05:00"))
            if o["route_id"] == "009"
        )
        assert exact["next_boarding_at"] == "2026-11-09T08:10:00-05:00"
        assert exact["time_basis"] == "frequency_exact"
        approximate = next(
            o
            for o in catalog.options("0001", when("2026-11-10T00:30:00-05:00"), window_minutes=10)
            if o["route_id"] == "008"
        )
        assert approximate["service_dates"] == ["2026-11-09"]
        assert approximate["next_boarding_at"] is None
        assert approximate["time_basis"] == "frequency_window_estimated"
        assert all(
            d["arrival_at"] is None and d["arrival_seconds"] is None
            for d in catalog.destinations(
                "0001",
                "008",
                0,
                approximate["pattern_id"],
                when("2026-11-10T00:30:00-05:00"),
                window_minutes=10,
            )
        )


def test_pickup_dropoff_and_unknown_direction(catalog_path):
    with Catalog(catalog_path) as catalog:
        options = catalog.options("0001", when())
        assert not {"003", "004", "007"} & {o["route_id"] for o in options}
        assert any(
            o["route_id"] == "004"
            for o in catalog.options("0001", when(), include_conditional=True)
        )
        unknown = next(o for o in options if o["route_id"] == "005")
        assert unknown["direction_id"] is None
        assert catalog.destinations("0001", "005", None, unknown["pattern_id"], when())


def test_loop_requires_origin_occurrence(catalog_path):
    with Catalog(catalog_path) as catalog:
        option = next(o for o in catalog.options("0001", when()) if o["route_id"] == "006")
        with pytest.raises(CatalogError, match="multiple"):
            catalog.destinations("0001", "006", 0, option["pattern_id"], when())
        result = catalog.destinations(
            "0001", "006", 0, option["pattern_id"], when(), origin_sequence=30
        )
        assert [r["stop_id"] for r in result] == ["0004"]


def test_inactive_expired_unknown_and_naive_queries_rejected(catalog_path):
    with Catalog(catalog_path) as catalog:
        option = main_pattern(catalog)
        with pytest.raises(CatalogError, match="eligible"):
            catalog.destinations(
                "0001",
                "001",
                0,
                option["pattern_id"],
                when("2026-11-09T12:00:00-05:00"),
                window_minutes=10,
            )
        with pytest.raises(CatalogError, match="timezone"):
            catalog.options("0001", datetime(2026, 11, 9, 8))
        with pytest.raises(CatalogError, match="Unknown"):
            catalog.options("DOES_NOT_EXIST", when())


def test_idempotency_does_not_modify_database(catalog_path):
    before = (file_hash(catalog_path), catalog_path.stat().st_mtime_ns)
    result = import_catalog(catalog_path.parent / "synthetic.zip", catalog_path)
    assert result["status"] == "reused"
    assert (file_hash(catalog_path), catalog_path.stat().st_mtime_ns) == before


def test_incompatible_existing_version_is_not_overwritten(catalog_path, catalog_tables):
    archive = write_zip(
        catalog_path.parent / "different.zip",
        {k: v for k, v in catalog_tables.items() if k != "frequencies.txt"},
    )
    before = file_hash(catalog_path)
    with pytest.raises(CatalogError, match="different"):
        import_catalog(archive, catalog_path)
    assert file_hash(catalog_path) == before


def test_orphan_reference_rolls_back_without_publishing(tmp_path, catalog_tables):
    catalog_tables["stop_times.txt"][1][0][2] = "NO_SUCH_STOP"
    database = tmp_path / "broken.sqlite3"
    with pytest.raises(CatalogError, match="orphan"):
        import_catalog(write_zip(tmp_path / "bad.zip", catalog_tables), database)
    assert not database.exists()
    assert list(tmp_path.glob("*.import-*")) == []


def test_missing_file_rejected(tmp_path, catalog_tables):
    catalog_tables.pop("trips.txt")
    with pytest.raises(CatalogError, match="Missing"):
        import_catalog(write_zip(tmp_path / "bad.zip", catalog_tables), tmp_path / "bad.sqlite3")


def test_calendar_dates_only_is_supported(tmp_path, catalog_tables):
    catalog_tables.pop("calendar.txt")
    catalog_tables["trips.txt"][1][:] = [
        r for r in catalog_tables["trips.txt"][1] if r[0] == "SPECIAL"
    ]
    catalog_tables["stop_times.txt"][1][:] = [
        r for r in catalog_tables["stop_times.txt"][1] if r[0] == "SPECIAL"
    ]
    catalog_tables.pop("frequencies.txt")
    database = tmp_path / "dates.sqlite3"
    import_catalog(write_zip(tmp_path / "dates.zip", catalog_tables), database)
    with Catalog(database) as catalog:
        assert catalog.active_services(date(2026, 11, 12)) == {"EX"}
        assert catalog.options("0001", when("2026-11-12T07:59:00-05:00"))


@pytest.mark.parametrize("clock,expected", [("25:00:00", 90000), ("49:10:00", 177000), ("", None)])
def test_time_conversion(clock, expected):
    assert gtfs_seconds(clock) == expected


@pytest.mark.parametrize("clock", ["24:60:00", "-1:00:00", "invalid"])
def test_invalid_gtfs_time(clock):
    with pytest.raises(CatalogError):
        gtfs_seconds(clock)


def test_cli_offline_demo(catalog_path, capsys):
    assert (
        main(
            [
                "--db",
                str(catalog_path),
                "demo",
                "A001",
                "--when",
                "2026-11-09T07:59:00-05:00",
                "--auto",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert '"destinations"' in output
    assert '"pattern_id"' in output
