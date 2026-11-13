from datetime import datetime, timedelta

import pytest
from google.transit import gtfs_realtime_pb2 as pb

from transmitracker.gtfs import FeedError
from transmitracker.gtfs.links import analyze_links
from transmitracker.gtfs.realtime import (
    decode_realtime,
    is_recent_snapshot,
    observations,
    summarize_realtime,
    timestamp_info,
)
from transmitracker.gtfs.static import read_static

NOW = datetime.fromisoformat("2026-11-12T07:00:00-05:00")


def fixture_feed(fixture_dir):
    return decode_realtime((fixture_dir / "synthetic_realtime.pb").read_bytes())


def test_decode_all_entity_types(fixture_dir):
    summary = summarize_realtime(fixture_feed(fixture_dir), now=NOW)
    assert summary["entities_by_kind"] == {"vehicle": 2, "trip_update": 1, "alert": 1}
    assert summary["header"]["freshness"] == "recent"
    assert summary["trip_update_samples"][0]["stops"][0]["stop_id"] == "DEMO_S1"


def test_absent_optional_fields_are_not_zero(fixture_dir):
    records = observations(fixture_feed(fixture_dir), now=NOW)
    assert records[0]["direction_id"] == 0
    assert records[1]["direction_id"] is None
    assert records[1]["latitude"] is None
    assert records[1]["reported"]["freshness"] == "unknown"
    assert records[1]["trip_id"] is None
    assert records[1]["vehicle_id"] != records[1]["entity_id"]


@pytest.mark.parametrize("payload", [b"", b"<html>maintenance</html>", b"\xff\xff\x80"])
def test_invalid_protobuf(payload):
    with pytest.raises(FeedError):
        decode_realtime(payload)


@pytest.mark.parametrize("age,expected", [(30, "recent"), (301, "stale"), (-90, "future")])
def test_freshness(age, expected):
    info = timestamp_info(int(NOW.timestamp()) - age, NOW)
    assert info["freshness"] == expected
    assert info["at_bogota"].endswith("-05:00")


def test_stale_vehicle_not_refreshed_by_header(fixture_dir):
    feed = fixture_feed(fixture_dir)
    feed.header.timestamp = int(NOW.timestamp())
    feed.entity[0].vehicle.timestamp = int((NOW - timedelta(hours=1)).timestamp())
    summary = summarize_realtime(feed, now=NOW)
    assert summary["header"]["freshness"] == "recent"
    assert summary["vehicle_freshness"]["stale"] == 1
    assert not is_recent_snapshot(summary)


def test_naive_time_rejected():
    with pytest.raises(ValueError, match="timezone"):
        timestamp_info(1, datetime(2026, 1, 1))


def test_valid_empty_feed_is_not_vehicle_evidence():
    feed = pb.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    decoded = decode_realtime(feed.SerializeToString())
    summary = summarize_realtime(decoded, now=NOW)
    assert summary["entity_count"] == 0
    assert not is_recent_snapshot(summary)


@pytest.mark.parametrize("bad_lat", [100, float("nan"), float("inf")])
def test_bad_coordinates(fixture_dir, bad_lat):
    feed = fixture_feed(fixture_dir)
    feed.entity[0].vehicle.position.latitude = bad_lat
    with pytest.raises(FeedError, match="coordinates"):
        decode_realtime(feed.SerializeToString())


def test_duplicate_entities(fixture_dir):
    feed = fixture_feed(fixture_dir)
    feed.entity[1].id = feed.entity[0].id
    with pytest.raises(FeedError, match="duplicate"):
        decode_realtime(feed.SerializeToString())


def test_id_joins_and_conflicts(fixture_dir):
    static = read_static(fixture_dir / "synthetic_gtfs.zip")
    feed = fixture_feed(fixture_dir)
    links = analyze_links(static, feed, now=NOW)
    assert links["vehicle_counts"]["trip_id_matched"] == 1
    assert links["examples"][0]["join_status"] == "trip_match"
    assert links["examples"][1]["join_status"] == "route_only"
    feed.entity[0].vehicle.trip.route_id = "DEMO_R2"
    links = analyze_links(static, feed, now=NOW)
    assert links["vehicle_counts"]["trip_route_conflicts"] == 1
    assert links["examples"][0]["join_status"] == "conflict"


def test_differential_and_deleted(fixture_dir):
    feed = fixture_feed(fixture_dir)
    feed.header.incrementality = pb.FeedHeader.DIFFERENTIAL
    feed.entity[0].is_deleted = True
    summary = summarize_realtime(feed, now=NOW)
    assert summary["warnings"]
    assert summary["entities_by_kind"]["deleted"] == 1
    assert len(observations(feed, now=NOW)) == 1
    assert not is_recent_snapshot(summary)


def test_trip_update_freshness_is_independent_of_header(fixture_dir):
    feed = fixture_feed(fixture_dir)
    feed.entity[2].trip_update.timestamp = int(NOW.timestamp()) - 1000
    summary = summarize_realtime(feed, now=NOW)
    assert summary["trip_update_freshness"] == {"stale": 1}
    assert summary["trip_updates_with_stops"] == 1
    assert summary["stop_time_update_count"] == 1
    assert not is_recent_snapshot(summary)


def test_trip_update_route_conflict(fixture_dir):
    feed = fixture_feed(fixture_dir)
    feed.entity[2].trip_update.trip.route_id = "DEMO_R2"
    links = analyze_links(read_static(fixture_dir / "synthetic_gtfs.zip"), feed, now=NOW)
    assert links["trip_update_counts"]["trip_route_conflicts"] == 1
