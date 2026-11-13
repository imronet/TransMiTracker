from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from transmitracker.gtfs import FeedError
from transmitracker.gtfs.static import read_static


def rewrite_zip(path, source, replacements=None, omit=()):
    with ZipFile(source) as original, ZipFile(path, "w", ZIP_DEFLATED) as target:
        for name in original.namelist():
            if name not in omit:
                target.writestr(name, (replacements or {}).get(name, original.read(name)))
    return path


def test_read_and_join_synthetic_static(fixture_dir):
    feed = read_static(fixture_dir / "synthetic_gtfs.zip")
    assert feed.summary["basic_checks_passed"]
    assert feed.summary["counts"]["routes.txt"] == 2
    assert feed.summary["counts"]["stop_times.txt"] == 2
    assert feed.trips["DEMO_T1"]["route_id"] == "DEMO_R1"
    assert feed.stops["DEMO_S1"]["parent_station"] == "DEMO_STATION"
    assert [s["stop_id"] for s in feed.sample_stops] == ["DEMO_S1", "DEMO_S2"]
    assert feed.sample_stops[0]["arrival_time"] == "25:00:00"


@pytest.mark.parametrize(
    "missing", ["routes.txt", "stops.txt", "trips.txt", "stop_times.txt", "calendar.txt"]
)
def test_missing_required_file(tmp_path, fixture_dir, missing):
    path = rewrite_zip(tmp_path / "broken.zip", fixture_dir / "synthetic_gtfs.zip", omit=[missing])
    with pytest.raises(FeedError, match="Missing"):
        read_static(path)


@pytest.mark.parametrize("payload", [b"<html>maintenance</html>", b"", b"PK\x03\x04truncated"])
def test_not_zip(tmp_path, payload):
    path = tmp_path / "broken.zip"
    path.write_bytes(payload)
    with pytest.raises(FeedError):
        read_static(path)


def test_size_bound(fixture_dir):
    with pytest.raises(FeedError, match="size"):
        read_static(fixture_dir / "synthetic_gtfs.zip", max_uncompressed=10)


@pytest.mark.parametrize(
    "replacement,reason",
    [
        ("route_name\nwrong\n", "missing columns"),
        ("route_id,route_type\nR,3\nR,3\n", "duplicate"),
        ("route_id,route_type\nR\n", "malformed"),
    ],
)
def test_bad_csv(tmp_path, fixture_dir, replacement, reason):
    path = rewrite_zip(
        tmp_path / "bad.zip", fixture_dir / "synthetic_gtfs.zip", {"routes.txt": replacement}
    )
    with pytest.raises(FeedError, match=reason):
        read_static(path)


def test_orphan_reference_is_reported(tmp_path, fixture_dir):
    source = (fixture_dir / "gtfs/trips.txt").read_text(encoding="utf-8")
    path = rewrite_zip(
        tmp_path / "orphan.zip",
        fixture_dir / "synthetic_gtfs.zip",
        {"trips.txt": source.replace("DEMO_R1", "UNKNOWN")},
    )
    feed = read_static(path)
    assert not feed.summary["basic_checks_passed"]
    assert feed.summary["reference_errors"]["trip_route_missing"] == 1


def test_utf8_bom(tmp_path, fixture_dir):
    content = (fixture_dir / "gtfs/stops.txt").read_bytes()
    path = rewrite_zip(
        tmp_path / "bom.zip",
        fixture_dir / "synthetic_gtfs.zip",
        {"stops.txt": b"\xef\xbb\xbf" + content},
    )
    assert "DEMO_S1" in read_static(path).stops
