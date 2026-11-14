import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from google.transit import gtfs_realtime_pb2 as pb

from transmitracker.research import local_pilot as pilot


def allowed_review(moment):
    return {
        "decision": "allowed_private_temporary",
        "scope": "one_local_session_12_positions_60s_no_redistribution",
        "evidence": ["https://example.invalid/SYNTHETIC-REVIEW"],
        "rationale": "SYNTHETIC TEST ONLY, not a real provider allowance",
        "reviewed_at": moment.isoformat(),
    }


def payload(ts=1800000000, *, missing=False, longitude=-74.1):
    feed = pb.FeedMessage()
    feed.header.gtfs_realtime_version = "2.0"
    feed.header.timestamp = ts
    entity = feed.entity.add()
    entity.id = "DEMO_ENTITY"
    if not missing:
        entity.vehicle.vehicle.id = "DEMO_BUS"
        entity.vehicle.timestamp = ts
    entity.vehicle.position.latitude = 4.65
    entity.vehicle.position.longitude = longitude
    entity.vehicle.trip.route_id = "DEMO_ROUTE"
    return feed.SerializeToString()


@pytest.fixture
def mocked_pilot(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "PILOT_ROOT", tmp_path)
    monkeypatch.setattr(pilot, "_SESSION_USED", False)
    state = {"time": 0, "calls": []}

    def handler(request):
        state["calls"].append((request.url.path, state["time"]))
        if request.url.path.endswith("manifest.json"):
            return httpx.Response(
                200,
                json={
                    "realtime_available": True,
                    "files": [
                        {"file_name": "positions.pb", "url": pilot.ENDPOINT, "available": True}
                    ],
                },
            )
        return httpx.Response(200, content=payload(1800000000 + state["time"]))

    client = httpx.Client(transport=httpx.MockTransport(handler))

    def sleep(seconds):
        state["time"] += seconds

    args = dict(
        confirm=True,
        client=client,
        clock=lambda: state["time"],
        sleep=sleep,
        now=lambda: datetime.fromtimestamp(1800000005 + state["time"], timezone.utc),
        permit=tmp_path / "permission.json",
    )
    pilot.create_permit(
        allowed_review(args["now"]()),
        tmp_path / "session",
        args["permit"],
        confirm=True,
        now=args["now"],
    )
    yield tmp_path, state, args
    client.close()


def test_default_and_confirmation_never_network(tmp_path, monkeypatch, capsys):
    assert pilot.main([]) == 0
    assert json.loads(capsys.readouterr().out)["network_requests"] == 0
    with pytest.raises(ValueError):
        pilot.collect(tmp_path / "blocked", confirm=True)
    assert not (tmp_path / "blocked").exists()
    with pytest.raises(ValueError):
        pilot.collect(tmp_path / "blocked", confirm=False)


@pytest.mark.parametrize("count,interval", [(0, 60), (13, 60), (True, 60), (2, 59), (2, 1.5)])
def test_strict_limits(count, interval):
    with pytest.raises(ValueError):
        pilot.limits(count, interval)


def test_max_requests_spacing_session_and_manifest(mocked_pilot):
    root, state, args = mocked_pilot
    session = pilot.collect(root / "session", count=12, interval=60, **args)
    assert session["positions_requests"] == 12
    assert session["manifest_requests"] == 1
    times = [t for path, t in state["calls"] if path.endswith("positions.pb")]
    assert times == list(range(0, 720, 60))
    with pytest.raises(ValueError, match="one session"):
        pilot.collect(root / "two", **args)
    assert len(state["calls"]) == 13
    record = json.loads((root / "session/capture_00.json").read_text())
    assert record["received_at"].endswith("+00:00")
    assert (
        record["vehicles"][0]["reported"]["timestamp"]
        != datetime.fromisoformat(record["received_at"]).timestamp()
    )


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503, 302])
def test_error_no_retry(mocked_pilot, status):
    root, state, args = mocked_pilot
    base = args["client"]._transport.handler

    def handler(request):
        if request.url.path.endswith("manifest.json"):
            return base(request)
        state["calls"].append((request.url.path, 0))
        return httpx.Response(status, headers={"Location": pilot.ENDPOINT})

    args["client"] = httpx.Client(transport=httpx.MockTransport(handler))
    try:
        report = pilot.collect(root / "session", count=12, **args)
    finally:
        args["client"].close()
    assert report["stop_reason"] == "error_no_retry"
    assert len(state["calls"]) == 2
    assert (root / "session/session.json").exists()


@pytest.mark.parametrize("body", [b"invalid", payload(longitude=190)])
def test_rejected_payload_preserved_and_no_retry(mocked_pilot, body):
    root, _, args = mocked_pilot
    base = args["client"]._transport.handler
    args["client"] = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: (
                base(r)
                if r.url.path.endswith("manifest.json")
                else httpx.Response(200, content=body)
            )
        )
    )
    try:
        result = pilot.collect(root / "session", **args)
    finally:
        args["client"].close()
    assert result["stop_reason"] == "decode_error"
    assert (root / "session/capture_00.pb").read_bytes() == body
    assert pilot.analyze(root / "session")["counts"]["undecodable_snapshots"] == 1


def test_stop_after_three_without_novelty(mocked_pilot):
    root, _, args = mocked_pilot
    base = args["client"]._transport.handler
    args["client"] = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: (
                base(r)
                if r.url.path.endswith("manifest.json")
                else httpx.Response(200, content=payload())
            )
        )
    )
    try:
        result = pilot.collect(root / "session", count=12, **args)
    finally:
        args["client"].close()
    assert result["positions_requests"] == 4  # first observation, then three repeated snapshots
    assert result["stop_reason"].startswith("three_snapshots")


def test_fixture_replay_integrity_filter_and_exclusive_files(tmp_path):
    directory = tmp_path / "demo"
    pilot.make_fixture(directory)
    report = pilot.analyze(directory)
    assert report == pilot.analyze(directory)
    assert report["counts"]["snapshots"] == 4
    assert report["counts"]["repeated_gps_timestamps"] == 1
    assert report["candidate_ids_with_three_distinct_times"]
    assert report["counts"]["plausible_displacement_candidates"] == 2
    assert report["network_requests"] == 0 and not report["real_operational_validation"]
    assert report["field_presence"]["start_date"]["absent"] == 4
    assert pilot.analyze(directory, routes=["UNKNOWN"])["counts"].get("observations", 0) == 0
    with pytest.raises(ValueError):
        pilot.analyze(directory, routes=["a", "b", "c"])
    with pytest.raises(FileExistsError):
        pilot.make_fixture(directory)
    (directory / "capture_00.pb").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256"):
        pilot.analyze(directory)


def test_missing_ids_and_times_not_filled(tmp_path):
    pilot.save_capture(
        payload(missing=True),
        tmp_path,
        0,
        received_at=datetime.now(timezone.utc),
        source="synthetic://test",
        origin="synthetic_fixture",
    )
    pilot.write_json(tmp_path / "session.json", {"captures": ["capture_00.json"]})
    report = pilot.analyze(tmp_path)
    assert report["counts"]["age_not_determinable"] == 1
    assert report["counts"]["unresolved_observations"] == 1
    assert not report["candidate_ids_with_three_distinct_times"]


def test_size_limit_transport_failure_and_manifest_host(mocked_pilot):
    root, _, args = mocked_pilot
    base = args["client"]._transport.handler
    args["client"] = httpx.Client(
        transport=httpx.MockTransport(
            lambda r: (
                base(r)
                if r.url.path.endswith("manifest.json")
                else httpx.Response(
                    200, headers={"Content-Length": str(pilot.MAX_BYTES + 1)}, content=b"x"
                )
            )
        )
    )
    try:
        report = pilot.collect(root / "session", **args)
    finally:
        args["client"].close()
    assert report["positions_requests"] == 1 and report["stop_reason"] == "error_no_retry"
    with pytest.raises(ValueError):
        pilot.endpoint_from_manifest(
            {
                "realtime_available": True,
                "files": [
                    {
                        "file_name": "positions.pb",
                        "url": "https://other.example/positions.pb",
                        "available": True,
                    }
                ],
            }
        )


def test_age_boundaries_and_backward_clock(tmp_path):
    names = []
    for number, (age, ts) in enumerate(
        [(119, 1000), (120, 1060), (300, 1120), (301, 1180), (-1, 1100)]
    ):
        pilot.save_capture(
            payload(ts),
            tmp_path,
            number,
            received_at=datetime.fromtimestamp(ts + age, timezone.utc),
            source="synthetic://test",
            origin="synthetic_fixture",
        )
        names.append(f"capture_{number:02}.json")
    pilot.write_json(tmp_path / "session.json", {"captures": names})
    counts = pilot.analyze(tmp_path)["counts"]
    assert [counts["age_" + k] for k in ("recent", "delayed", "old", "future")] == [1, 2, 1, 1]
    assert counts["time_regression"] == 1


def test_timeout_and_bad_manifest_stop_without_positions(mocked_pilot):
    root, state, args = mocked_pilot

    def timeout(request):
        state["calls"].append(request.url.path)
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    args["client"] = httpx.Client(transport=httpx.MockTransport(timeout))
    try:
        result = pilot.collect(root / "session", **args)
    finally:
        args["client"].close()
    assert result["positions_requests"] == 0
    assert len(state["calls"]) == 1
    assert result["failed_download"]["attempts"] == 1


def test_paths_and_missing_status(tmp_path):
    pilot.save_capture(
        payload(),
        tmp_path,
        0,
        received_at=datetime.fromtimestamp(1800000005, timezone.utc),
        source="synthetic://test",
        origin="synthetic_fixture",
    )
    record = json.loads((tmp_path / "capture_00.json").read_text())
    assert record["vehicles"][0]["current_status"] is None
    record["receipt_timestamp_verified"] = False
    (tmp_path / "capture_00.json").write_text(json.dumps(record))
    pilot.write_json(tmp_path / "session.json", {"captures": ["capture_00.json"]})
    with pytest.raises(ValueError, match="Reception"):
        pilot.analyze(tmp_path)
    record["receipt_timestamp_verified"] = True
    record["raw_file"] = "../outside.pb"
    (tmp_path / "capture_00.json").write_text(json.dumps(record))
    with pytest.raises(ValueError, match="path"):
        pilot.analyze(tmp_path)


@pytest.mark.parametrize("change", ["expired", "future", "directory", "endpoint", "conditions"])
def test_permit_invalid_never_creates_client(mocked_pilot, monkeypatch, change):
    root, state, args = mocked_pilot
    value = json.loads(args["permit"].read_text())
    if change == "expired":
        state["time"] = 901
    elif change == "future":
        value["issued_at"] = "2030-01-01T00:00:00+00:00"
        value["expires_at"] = "2030-01-01T00:15:00+00:00"
    elif change == "directory":
        value["directory"] = str(root / "other")
    elif change == "endpoint":
        value["endpoint"] = "https://example.invalid/positions.pb"
    else:
        value["review"]["decision"] = "unresolved"
    args["permit"].write_text(json.dumps(value))
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: pytest.fail("No client expected"))
    args.pop("client")
    with pytest.raises(ValueError):
        pilot.collect(root / "session", **args)
    assert not (root / "session").exists()


def test_permit_atomic_claim_survives_new_process_flag(mocked_pilot, monkeypatch):
    root, _, args = mocked_pilot
    pilot.claim_permit(args["permit"], root / "session", count=12, interval=60, now=args["now"])
    monkeypatch.setattr(pilot, "_SESSION_USED", False)
    with pytest.raises(FileExistsError):
        pilot.collect(root / "session", **args)
    assert not (root / "session").exists()


def test_issuance_requires_resolution_confirmation_and_new_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "PILOT_ROOT", tmp_path)
    moment = datetime.now(timezone.utc)
    review = allowed_review(moment)
    for confirm, decision in [(False, "allowed_private_temporary"), (True, "unresolved")]:
        review["decision"] = decision
        with pytest.raises(ValueError):
            pilot.create_permit(
                review, tmp_path / "session", tmp_path / "permit.json", confirm=confirm
            )
    assert not (tmp_path / "permit.json").exists()
    review["decision"] = "allowed_private_temporary"
    value = pilot.create_permit(
        review, tmp_path / "session", tmp_path / "permit.json", confirm=True
    )
    assert (
        datetime.fromisoformat(value["expires_at"]) - datetime.fromisoformat(value["issued_at"])
    ).total_seconds() == 900
    with pytest.raises(FileExistsError):
        pilot.create_permit(review, tmp_path / "session", tmp_path / "permit.json", confirm=True)


def test_interrupt_consumes_permission_and_preserves_session(mocked_pilot):
    root, _, args = mocked_pilot

    def interrupt(request):
        raise KeyboardInterrupt()

    client = httpx.Client(transport=httpx.MockTransport(interrupt))
    args["client"] = client
    try:
        result = pilot.collect(root / "session", **args)
    finally:
        client.close()
    assert result["stop_reason"] == "operator_interrupted"
    assert (root / "session/session.json").exists()
    assert args["permit"].with_suffix(".json.used").exists()


def test_session_data_ignored_by_git():
    import subprocess

    result = subprocess.run(
        [
            "git",
            "check-ignore",
            "data/pilots/private/session.json",
            "data/pilots/private/capture_00.pb",
        ],
        cwd=pilot.ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 2


@pytest.mark.parametrize("elapsed", [899, 900, 901])
def test_real_fifteen_minute_window(mocked_pilot, elapsed):
    root, state, args = mocked_pilot
    original = json.loads(args["permit"].read_text())
    state["time"] = elapsed
    if elapsed < 900:
        pilot.claim_permit(args["permit"], root / "session", count=12, interval=60, now=args["now"])
    else:
        with pytest.raises(ValueError, match="expired"):
            pilot.claim_permit(
                args["permit"], root / "session", count=12, interval=60, now=args["now"]
            )
    assert json.loads(args["permit"].read_text()) == original
    assert state["calls"] == []


def test_review_expires_after_seven_days(mocked_pilot):
    root, _, args = mocked_pilot
    value = json.loads(args["permit"].read_text())
    value["review"]["reviewed_at"] = (args["now"]() - timedelta(days=7, seconds=1)).isoformat()
    args["permit"].write_text(json.dumps(value))
    with pytest.raises(ValueError, match="seven days"):
        pilot.claim_permit(args["permit"], root / "session", count=12, interval=60, now=args["now"])
    with pytest.raises(ValueError, match="seven days"):
        pilot.create_permit(
            value["review"], root / "session", root / "new.json", confirm=True, now=args["now"]
        )
    assert not args["permit"].with_suffix(".json.used").exists()


@pytest.mark.parametrize("target", ["../public.json", "nested/../../escape.json"])
def test_full_diagnostics_cannot_escape_private_root(tmp_path, monkeypatch, target):
    private = tmp_path / "pilots"
    private.mkdir()
    monkeypatch.setattr(pilot, "PILOT_ROOT", private)
    monkeypatch.setattr(pilot, "project_path", lambda p: Path(p).resolve())
    output = private / target
    with pytest.raises(SystemExit) as error:
        pilot.main(["analyze", str(private / "missing"), "--output", str(output)])
    assert error.value.code == 2
    assert not output.resolve().exists()


def test_full_diagnostic_private_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(pilot, "PILOT_ROOT", tmp_path)
    monkeypatch.setattr(pilot, "project_path", lambda p: Path(p).resolve())
    pilot.make_fixture(tmp_path / "input")
    output = tmp_path / "reports/result.json"
    assert pilot.main(["analyze", str(tmp_path / "input"), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["origins"] == ["synthetic_fixture"]
