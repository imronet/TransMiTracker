"""Manual GPS pilot preparation. Default is a network-free plan; no scheduler."""

import argparse
import hashlib
import json
import math
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx

from transmitracker.diagnostics import ROOT, project_path
from transmitracker.providers.http import DownloadError, download
from transmitracker.research.temporal import capture_record, distance_m

MANIFEST = "https://gtfs.transmilenio.gov.co/manifest.json"
ENDPOINT = "https://gtfs.transmilenio.gov.co/positions.pb"
PILOT_ROOT = ROOT / "data/pilots"
BLOCK_REASON = "Public conditions do not yet resolve bounded polling and local retention."
_SESSION_USED = False
MAX_BYTES = 8 * 1024**2


def utc_now():
    return datetime.now(timezone.utc)


def decode_capture(payload, **kwargs):
    record = capture_record(payload, **kwargs)
    for row in record["vehicles"]:
        if "current_status" not in row["reported_fields"]:
            row["current_status"] = None
    return record


def write_json(path, value):
    """Exclusive files: neither historical evidence nor other sessions are overwritten."""
    with Path(path).open("x", encoding="utf-8") as target:
        json.dump(value, target, ensure_ascii=False, indent=2, allow_nan=False)
        target.write("\n")


def pilot_path(path):
    path = Path(path).resolve()
    if not path.is_relative_to(PILOT_ROOT.resolve()) or path == PILOT_ROOT.resolve():
        raise ValueError("Session and permit must be children of data/pilots")
    return path


def check_review(review, now):
    if (
        review.get("decision") != "allowed_private_temporary"
        or review.get("scope") != "one_local_session_12_positions_60s_no_redistribution"
        or not isinstance(review.get("evidence"), list)
        or not review["evidence"]
        or not isinstance(review.get("rationale"), str)
        or not review["rationale"].strip()
    ):
        raise ValueError("Conditions unresolved: " + BLOCK_REASON)
    reviewed = datetime.fromisoformat(review["reviewed_at"])
    if reviewed.utcoffset() is None or not 0 <= (now - reviewed).total_seconds() <= 7 * 86400:
        raise ValueError("Conditions review must be dated within seven days")


def create_permit(review, directory, permit, *, confirm=False, now=utc_now):
    """Offline, explicit operator decision; not a provider license or remote authorization."""
    moment = now()
    if not confirm:
        raise ValueError("Explicit single-session confirmation required")
    check_review(review, moment)
    directory, permit = pilot_path(directory), pilot_path(permit)
    if directory.exists() or permit.is_relative_to(directory):
        raise ValueError("Session must be new and permit must be outside it")
    value = {
        "schema_version": 1,
        "permit_id": uuid4().hex,
        "directory": str(directory),
        "endpoint": ENDPOINT,
        "manifest": MANIFEST,
        "issued_at": moment.isoformat(),
        "expires_at": (moment + timedelta(minutes=15)).isoformat(),
        "maximum_positions": 12,
        "minimum_interval": 60,
        "review": review,
    }
    permit.parent.mkdir(parents=True, exist_ok=True)
    write_json(permit, value)
    return value


def claim_permit(permit, directory, *, count, interval, now):
    permit, directory = pilot_path(permit), pilot_path(directory)
    value = json.loads(permit.read_text(encoding="utf-8"))
    moment = now()
    issued = datetime.fromisoformat(value["issued_at"])
    expires = datetime.fromisoformat(value["expires_at"])
    if (
        value.get("schema_version") != 1
        or value.get("endpoint") != ENDPOINT
        or value.get("manifest") != MANIFEST
        or value.get("directory") != str(directory)
        or directory.exists()
        or issued.utcoffset() is None
        or expires.utcoffset() is None
        or not issued <= moment < expires
        or not 0 < (expires - issued).total_seconds() <= 900
        or value.get("maximum_positions") != 12
        or value.get("minimum_interval") != 60
    ):
        raise ValueError("Permit expired, invalid, or bound to another session")
    check_review(value["review"], moment)
    limits(count, interval)
    # Exclusive creation is the cross-process one-use claim. Never auto-remove it,
    # even after a failure; copying the permission still binds the same new directory.
    write_json(
        permit.with_suffix(permit.suffix + ".used"),
        {
            "permit_id": value["permit_id"],
            "claimed_at": moment.isoformat(),
            "permit_sha256": hashlib.sha256(permit.read_bytes()).hexdigest(),
        },
    )
    return value


def limits(count, interval, routes=()):
    if type(count) is not int or not 1 <= count <= 12:
        raise ValueError("Positions count must be 1..12")
    if type(interval) is not int or interval < 60:
        raise ValueError("Interval must be an integer >=60 seconds")
    if len(routes) > 2 or any(not isinstance(r, str) or not r for r in routes):
        raise ValueError("Select at most two exact published route IDs")


def endpoint_from_manifest(value):
    candidates = [f for f in value["files"] if f.get("file_name") == "positions.pb"]
    if len(candidates) != 1 or candidates[0].get("url") != ENDPOINT:
        raise ValueError(
            "Manifest positions endpoint missing, ambiguous or changed; review required"
        )
    if value.get("realtime_available") is not True or candidates[0].get("available") is not True:
        raise ValueError("Manifest reports unavailable positions")
    return candidates[0]["url"]


def save_capture(payload, directory, number, *, received_at, source, origin, http=None):
    if received_at.utcoffset() is None:
        raise ValueError("Reception requires timezone")
    received_at = received_at.astimezone(timezone.utc)
    name = f"capture_{number:02}"
    raw = directory / (name + ".pb")
    with raw.open("xb") as target:
        target.write(payload)
    record = {
        "capture_id": name,
        "raw_file": raw.name,
        "source": source,
        "origin": origin,
        "received_at": received_at.isoformat(),
        "receipt_timestamp_verified": True,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "download_status": "downloaded",
        "http": http,
    }
    try:
        decoded = decode_capture(payload, received_at=received_at, source=source, origin=origin)
        record.update(decoded)
        record["decode_status"] = "decoded"
    except ValueError as error:
        record.update(decode_status="rejected", decode_error=str(error))
    write_json(directory / (name + ".json"), record)
    return record


def novelty(record, latest, routes):
    """New GPS times, not new reception times or changed entity IDs."""
    new = 0
    for row in record.get("vehicles", []):
        if routes and row["route_id"] not in routes:
            continue
        stamp = row["reported"]["timestamp"]
        if not row["vehicle_id"] or stamp is None:
            continue
        key = (record["source"], row["vehicle_id"])
        if stamp > latest.get(key, -math.inf):
            latest[key] = stamp
            new += 1
    return new


def collect(
    directory,
    *,
    confirm=False,
    count=3,
    interval=60,
    routes=(),
    permit=None,
    client=None,
    clock=time.monotonic,
    sleep=time.sleep,
    now=utc_now,
):
    """One sequential session; HTTP at most 1 manifest + 12 positions, no retries.

    Dependencies are injectable solely for offline testing. The CLI cannot bypass
    the conditions gate. Any download/decode error stops this exploratory session.
    """
    global _SESSION_USED
    limits(count, interval, routes)
    if not confirm or permit is None:
        raise ValueError(
            "Capture blocked: explicit confirmation and resolved conditions required. "
            + BLOCK_REASON
        )
    if _SESSION_USED:
        raise ValueError("Only one session per process")
    directory = pilot_path(directory)
    permission = claim_permit(permit, directory, count=count, interval=interval, now=now)
    directory.mkdir(parents=True, exist_ok=False)
    _SESSION_USED = True
    own = client is None
    client = client or httpx.Client(
        follow_redirects=False,
        trust_env=False,
        headers={"User-Agent": "TransMiTracker-local-pilot-P0"},
    )
    session = {
        "schema_version": 1,
        "session_id": directory.name,
        "origin": "real_network_capture",
        "planned_positions": count,
        "interval_seconds": interval,
        "routes": list(routes),
        "manifest_requests": 0,
        "positions_requests": 0,
        "captures": [],
        "stop_reason": "limit_reached",
        "conditions_review": permission["review"],
        "permit_id": permission["permit_id"],
    }
    latest, unchanged, previous = {}, 0, None
    try:
        session["manifest_requests"] += 1
        metadata = download(
            client,
            MANIFEST,
            directory / "provider_manifest.json",
            attempts=1,
            max_bytes=65536,
            deadline_seconds=15,
        )
        session["manifest_download"] = vars(metadata)
        endpoint = endpoint_from_manifest(
            json.loads((directory / "provider_manifest.json").read_text(encoding="utf-8"))
        )
        for number in range(count):
            if previous is not None:
                while clock() - previous < interval:
                    sleep(min(1, interval - (clock() - previous)))
            previous = clock()
            session["positions_requests"] += 1
            requested_at = now().astimezone(timezone.utc).isoformat()
            temporary = directory / f"download_{number:02}.pb"
            result = download(
                client, endpoint, temporary, attempts=1, max_bytes=MAX_BYTES, deadline_seconds=15
            )
            received = now()  # after the response body has been completely received
            payload = temporary.read_bytes()
            record = save_capture(
                payload,
                directory,
                number,
                received_at=received,
                source=endpoint,
                origin="real_network_capture",
                http={**vars(result), "requested_at": requested_at},
            )
            temporary.unlink()
            session["captures"].append(f"capture_{number:02}.json")
            if record["decode_status"] != "decoded":
                session["stop_reason"] = "decode_error"
                break
            new = novelty(record, latest, routes)
            unchanged = 0 if new else unchanged + 1
            if unchanged >= 3:
                session["stop_reason"] = "three_snapshots_without_new_relevant_gps_times"
                break
    except KeyboardInterrupt:
        session["stop_reason"] = "operator_interrupted"
    except (DownloadError, ValueError, KeyError, OSError) as error:
        session["stop_reason"] = "error_no_retry"
        session["error_type"] = type(error).__name__
        if isinstance(error, DownloadError):
            session["failed_download"] = error.result
    finally:
        if own:
            client.close()
        write_json(directory / "session.json", session)
    return session


def analyze(directory, *, routes=(), recent=120, delayed=300, max_speed=35):
    """Deterministic parsing from original bytes, not trusted cached vehicle JSON."""
    limits(1, 60, routes)
    if not 0 < recent < delayed or not math.isfinite(max_speed) or max_speed <= 0:
        raise ValueError("Invalid exploratory thresholds")
    directory = Path(directory).resolve()
    session = json.loads((directory / "session.json").read_text(encoding="utf-8"))
    counts, presence, ages, previous, seen, instants = (
        Counter(),
        defaultdict(Counter),
        [],
        {},
        set(),
        defaultdict(set),
    )
    snapshots, pairs, origins = [], [], set()
    for name in session["captures"]:
        path = (directory / name).resolve()
        if not path.is_relative_to(directory):
            raise ValueError("Record path escapes session")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("receipt_timestamp_verified") is not True:
            raise ValueError("Reception time is not verified; cannot assess GPS age")
        raw = (directory / record["raw_file"]).resolve()
        if not raw.is_relative_to(directory) or raw.stat().st_size > MAX_BYTES:
            raise ValueError("Invalid payload path or size")
        payload = raw.read_bytes()
        if hashlib.sha256(payload).hexdigest() != record["payload_sha256"]:
            raise ValueError("Payload SHA-256 mismatch")
        origins.add(record["origin"])
        received = datetime.fromisoformat(record["received_at"])
        counts["snapshots"] += 1
        try:
            rebuilt = decode_capture(
                payload, received_at=received, source=record["source"], origin=record["origin"]
            )
        except ValueError as error:
            counts["undecodable_snapshots"] += 1
            snapshots.append(
                {"capture": name, "classification": "not_determinable", "error": str(error)}
            )
            previous.clear()
            continue
        counts["decodable_snapshots"] += 1
        current, fresh = {}, 0
        vehicles = [r for r in rebuilt["vehicles"] if not routes or r["route_id"] in routes]
        counts["observations_before_filter"] += len(rebuilt["vehicles"])
        groups = Counter(r["vehicle_id"] for r in vehicles if r["vehicle_id"])
        for row in vehicles:
            counts["observations"] += 1
            for key in (
                "vehicle_id",
                "trip_id",
                "route_id",
                "start_date",
                "start_time",
                "stop_id",
                "current_stop_sequence",
                "current_status",
                "latitude",
                "longitude",
            ):
                presence[key]["present" if row[key] is not None else "absent"] += 1
            ts = row["reported"]["timestamp"]
            presence["gps_timestamp"]["present" if ts is not None else "absent"] += 1
            age = received.timestamp() - ts if ts is not None else None
            label = (
                "not_determinable"
                if age is None
                else "future"
                if age < 0
                else "recent"
                if age < recent
                else "delayed"
                if age <= delayed
                else "old"
            )
            counts["age_" + label] += 1
            if age is not None:
                ages.append(age)
            vehicle = row["vehicle_id"]
            if not vehicle or groups[vehicle] != 1 or ts is None:
                counts["unresolved_observations"] += 1
                continue
            key = (record["source"], vehicle)
            signature = (*key, ts)
            if signature in seen:
                counts["repeated_gps_timestamps"] += 1
            elif not instants[key] or ts > max(instants[key]):
                fresh += 1
            seen.add(signature)
            instants[key].add(ts)
            current[key] = row
            old = previous.get(key)
            if old:
                counts["reappearing_candidate_observations"] += 1
                delta = ts - old["reported"]["timestamp"]
                descriptor_changed = any(
                    row[k] != old[k] for k in ("trip_id", "route_id", "start_date", "start_time")
                )
                coordinates = (old["latitude"], old["longitude"], row["latitude"], row["longitude"])
                distance = (
                    distance_m(coordinates[:2], coordinates[2:])
                    if None not in coordinates
                    else None
                )
                speed = distance / delta if distance is not None and delta > 0 else None
                if distance is not None:
                    counts[
                        "changed_position_pairs" if distance > 0 else "unchanged_position_pairs"
                    ] += 1
                plausible = (
                    not descriptor_changed
                    and delta > 0
                    and distance is not None
                    and distance > 0
                    and speed <= max_speed
                    and age is not None
                    and 0 <= age <= delayed
                    and delta <= delayed
                )
                reason = (
                    "descriptor_change"
                    if descriptor_changed
                    else "time_regression"
                    if delta < 0
                    else "same_timestamp_position_conflict"
                    if delta == 0 and distance
                    else "gap"
                    if delta > delayed
                    else "implausible_speed"
                    if speed is not None and speed > max_speed
                    else "observed_pair"
                )
                counts[reason] += 1
                if plausible:
                    counts["plausible_displacement_candidates"] += 1
                pairs.append(
                    {
                        "vehicle_id": vehicle,
                        "classification": "candidate" if plausible else "not_determinable",
                        "delta_gps_s": delta,
                        "distance_m": round(distance, 3) if distance is not None else None,
                        "mean_speed_mps": round(speed, 3) if speed is not None else None,
                        "reason": reason,
                    }
                )
        snapshots.append(
            {
                "capture": name,
                "received_at": record["received_at"],
                "feed_timestamp": rebuilt["feed"]["timestamp"],
                "observations": len(vehicles),
                "new_gps_times": fresh,
                "classification": "observation",
            }
        )
        # Retain history for reappearance; absence does not assert identity or arrival.
        previous.update(current)
    if len(origins) > 1:
        raise ValueError("Do not mix synthetic and real sessions")
    return {
        "schema_version": 1,
        "origins": sorted(origins),
        "network_requests": 0,
        "real_operational_validation": False,
        "counts": dict(sorted(counts.items())),
        "thresholds": {
            "recent_lt_s": recent,
            "delayed_through_s": delayed,
            "max_candidate_speed_mps": max_speed,
        },
        "field_presence": {
            k: {"present": v["present"], "absent": v["absent"], "explicit_null": 0}
            for k, v in sorted(presence.items())
        },
        "null_semantics": "Protobuf has absence, not JSON null; absent values stay absent",
        "gps_ages_s": ages,
        "snapshots": snapshots,
        "pairs": pairs,
        "candidate_ids_with_three_distinct_times": sorted(
            f"{k[0]}|{k[1]}" for k, values in instants.items() if len(values) >= 3
        ),
        "route_filter": list(routes),
        "route_scope": "Exact published route_id only; no GTFS crosswalk or operational identity proven",
        "inferences_excluded": ["arrivals", "boarding", "travel_durations", "passenger_wait"],
    }


def make_fixture(directory):
    """Tiny synthetic evidence, never a fallback for a network failure."""
    from google.transit import gtfs_realtime_pb2 as pb

    directory.mkdir(parents=True, exist_ok=False)
    names = []
    for index, step in enumerate((0, 60, 60, 120)):
        feed = pb.FeedMessage()
        feed.header.gtfs_realtime_version = "2.0"
        feed.header.timestamp = 1800000000 + step
        entity = feed.entity.add()
        entity.id = "DEMO_ENTITY"
        entity.vehicle.vehicle.id = "DEMO_BUS"
        entity.vehicle.trip.trip_id = "DEMO_TRIP"
        entity.vehicle.trip.route_id = "DEMO_ROUTE"
        entity.vehicle.timestamp = feed.header.timestamp
        entity.vehicle.position.latitude = 4.65
        entity.vehicle.position.longitude = -74.1 + step * 0.00001
        save_capture(
            feed.SerializeToString(),
            directory,
            index,
            received_at=datetime.fromtimestamp(1800000005 + index * 60, timezone.utc),
            source="synthetic://local-pilot",
            origin="synthetic_fixture",
        )
        names.append(f"capture_{index:02}.json")
    write_json(
        directory / "session.json",
        {
            "schema_version": 1,
            "origin": "synthetic_fixture",
            "captures": names,
            "network_requests": 0,
        },
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command")
    fixture = sub.add_parser("fixture", help="Generate explicitly synthetic Protobuf files offline")
    fixture.add_argument("--directory", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--confirm-real-capture", action="store_true")
    capture.add_argument("--permit", help="Local expiring one-use permission; no default")
    capture.add_argument("--count", type=int, default=3)
    capture.add_argument("--interval", type=int, default=60)
    capture.add_argument("--directory", default="data/pilots/" + uuid4().hex)
    capture.add_argument("--route", action="append", default=[])
    authorize = sub.add_parser(
        "permit", help="Offline issuance, only after conditions are resolved"
    )
    authorize.add_argument("--review", required=True)
    authorize.add_argument("--directory", required=True)
    authorize.add_argument("--output", required=True)
    authorize.add_argument("--confirm-one-session", action="store_true")
    offline = sub.add_parser("analyze")
    offline.add_argument("directory")
    offline.add_argument("--output", required=True)
    offline.add_argument("--route", action="append", default=[])
    offline.add_argument("--recent", type=int, default=120)
    offline.add_argument("--delayed", type=int, default=300)
    args = parser.parse_args(argv)
    try:
        if args.command is None:
            print(
                json.dumps(
                    {
                        "mode": "offline_plan",
                        "network_requests": 0,
                        "capture_enabled": False,
                        "reason": BLOCK_REASON,
                    }
                )
            )
            return 0
        if args.command == "permit":
            review = json.loads(project_path(args.review).read_text(encoding="utf-8"))
            create_permit(
                review,
                project_path(args.directory),
                project_path(args.output),
                confirm=args.confirm_one_session,
            )
            return 0
        if args.command == "fixture":
            make_fixture(project_path(args.directory))
            return 0
        if args.command == "capture":
            result = collect(
                project_path(args.directory),
                confirm=args.confirm_real_capture,
                count=args.count,
                interval=args.interval,
                routes=args.route,
                permit=project_path(args.permit) if args.permit else None,
            )
            print(json.dumps({"stop_reason": result["stop_reason"]}))
            return 0 if result["stop_reason"] == "limit_reached" else 1
        output = pilot_path(project_path(args.output))
        report = analyze(
            project_path(args.directory),
            routes=args.route,
            recent=args.recent,
            delayed=args.delayed,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        write_json(output, report)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"Pilot input rejected ({type(error).__name__}); no automatic retry.\n")


if __name__ == "__main__":
    raise SystemExit(main())
