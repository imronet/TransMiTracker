import json
import sqlite3
from datetime import timedelta

import pytest

from transmitracker.gtfs import FeedError
from transmitracker.gtfs.realtime import decode_realtime, observations
from transmitracker.research.scenarios import synthetic_snapshots
from transmitracker.research.snapshots import identity, ingest_snapshot


def scenario(fixture_dir):
    return json.loads((fixture_dir / "snapshot_sequence.json").read_text(encoding="utf-8"))


def test_simultaneous_vehicles_and_trip_change(fixture_dir):
    results = []
    with sqlite3.connect(":memory:") as connection:
        for captured, payload in synthetic_snapshots(scenario(fixture_dir)):
            results.append(
                ingest_snapshot(
                    connection,
                    payload,
                    provider="synthetic",
                    captured_at=captured,
                    route_ids={"SYN_R1"},
                )
            )
        assert [r["inserted"] for r in results] == [2, 2, 1]
        assert results[2]["quarantined_identity"] == 1
        assert results[2]["rejected_timestamp"] == 1
        assert connection.execute("SELECT COUNT(*) FROM journeys").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 5
        # V2 disappearance does not produce an invented arrival or observation.
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM observations WHERE mapping_status='unresolved'"
            ).fetchone()[0]
            == 5
        )


def test_repeated_payload_is_not_new_movement(fixture_dir):
    captured, payload = next(synthetic_snapshots(scenario(fixture_dir)))
    with sqlite3.connect(":memory:") as connection:
        first = ingest_snapshot(
            connection, payload, provider="synthetic", captured_at=captured, route_ids={"SYN_R1"}
        )
        replay = ingest_snapshot(
            connection, payload, provider="synthetic", captured_at=captured, route_ids={"SYN_R1"}
        )
        later = ingest_snapshot(
            connection,
            payload,
            provider="synthetic",
            captured_at=captured + timedelta(seconds=40),
            route_ids={"SYN_R1"},
        )
        assert first["inserted"] == 2
        assert replay["replayed_snapshot"]
        assert later["duplicate"] == 2
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2


@pytest.mark.parametrize(
    "key,new",
    [
        ("vehicle_id", "OTHER"),
        ("trip_id", "OTHER"),
        ("start_date", "20261113"),
        ("start_time", "25:00:00"),
        ("route_id", "OTHER"),
        ("direction_id", 1),
        ("schedule_relationship", 2),
    ],
)
def test_identity_separates_instances(fixture_dir, key, new):
    captured, payload = next(synthetic_snapshots(scenario(fixture_dir)))
    record = observations(decode_realtime(payload), now=captured)[0]
    assert identity(record, "a") != identity({**record, key: new}, "a")
    assert identity(record, "a") != identity(record, "b")


def test_identity_does_not_infer_service_date(fixture_dir):
    captured, payload = next(synthetic_snapshots(scenario(fixture_dir)))
    record = observations(decode_realtime(payload), now=captured)[0]
    with pytest.raises(ValueError, match="identity"):
        identity({**record, "start_date": None}, "a")


def test_conflicting_timestamp_is_not_overwritten(fixture_dir):
    captured, payload = next(synthetic_snapshots(scenario(fixture_dir)))
    feed = decode_realtime(payload)
    feed.entity[0].vehicle.position.latitude += 0.001
    with sqlite3.connect(":memory:") as connection:
        ingest_snapshot(
            connection, payload, provider="synthetic", captured_at=captured, route_ids={"SYN_R1"}
        )
        result = ingest_snapshot(
            connection,
            feed.SerializeToString(),
            provider="synthetic",
            captured_at=captured,
            route_ids={"SYN_R1"},
        )
        assert result["timestamp_conflict"] == 1
        assert result["duplicate"] == 1
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 2


def test_out_of_order_is_quarantined(fixture_dir):
    snapshots = list(synthetic_snapshots(scenario(fixture_dir)))
    with sqlite3.connect(":memory:") as connection:
        for index in (1, 0):
            captured, payload = snapshots[index]
            result = ingest_snapshot(
                connection,
                payload,
                provider="synthetic",
                captured_at=captured,
                route_ids={"SYN_R1"},
            )
        assert result["quarantined_out_of_order"] == 2


def test_old_header_does_not_refresh_old_observations(fixture_dir):
    captured, payload = next(synthetic_snapshots(scenario(fixture_dir)))
    with sqlite3.connect(":memory:") as connection:
        result = ingest_snapshot(
            connection,
            payload,
            provider="synthetic",
            captured_at=captured + timedelta(hours=1),
            route_ids={"SYN_R1"},
        )
        assert result == {"rejected_header": 1}
        assert connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 0


def test_differential_not_treated_as_complete(fixture_dir):
    captured, payload = next(synthetic_snapshots(scenario(fixture_dir)))
    feed = decode_realtime(payload)
    feed.header.incrementality = 1
    with sqlite3.connect(":memory:") as connection, pytest.raises(FeedError):
        ingest_snapshot(
            connection,
            feed.SerializeToString(),
            provider="synthetic",
            captured_at=captured,
            route_ids={"SYN_R1"},
        )


def test_filter_is_explicit_and_excludes_other_routes(fixture_dir):
    captured, payload = next(synthetic_snapshots(scenario(fixture_dir)))
    with sqlite3.connect(":memory:") as connection:
        with pytest.raises(ValueError, match="filter"):
            ingest_snapshot(
                connection, payload, provider="synthetic", captured_at=captured, route_ids=set()
            )
        result = ingest_snapshot(
            connection, payload, provider="synthetic", captured_at=captured, route_ids={"OTHER"}
        )
        assert result["filtered_out"] == 2
