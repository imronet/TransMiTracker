"""Bounded diagnostic capture, never a production collector or scheduled service."""

import argparse
import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import httpx

from transmitracker.catalog.common import BOGOTA
from transmitracker.catalog.queries import Catalog
from transmitracker.diagnostics import project_path
from transmitracker.providers.http import DownloadError, download
from transmitracker.research.temporal import TemporalAnalyzer, capture_record

ENDPOINT = "https://gtfs.transmilenio.gov.co/positions.pb"


def validate_limits(count: int, interval: int):
    if type(count) is not int or not 2 <= count <= 16:
        raise ValueError("Capture count must be 2..16")
    if type(interval) is not int or interval < 60 or (count - 1) * interval > 900:
        raise ValueError("Interval must be >=60s and the proposed span <=900s")


def check_review(review: dict, count: int, interval: int):
    validate_limits(count, interval)
    if review.get("decision") != "bounded_test_allowed" or not review.get("evidence"):
        raise ValueError("Provider conditions have not established allowance for this bounded test")
    if (
        review.get("endpoint") != ENDPOINT
        or interval < review.get("minimum_interval_seconds", 9001)
        or count > review.get("maximum_captures", 0)
    ):
        raise ValueError("Experiment exceeds the conditions review")
    reviewed = datetime.fromisoformat(review["reviewed_at"])
    if (
        reviewed.tzinfo is None
        or not 0 <= (datetime.now(BOGOTA) - reviewed).total_seconds() <= 7 * 86400
    ):
        raise ValueError("Review must be timezone-aware and no older than seven days")


def collect(
    review: dict,
    directory: Path,
    *,
    count=3,
    interval=60,
    clock=time.monotonic,
    sleep=time.sleep,
    now=None,
    client=None,
):
    """One attempt per capture, no catch-up and no retry after errors/429.

    Reserve 60 s before the 15-minute deadline for bounded HTTP completion.
    A request can use up to the transport timeout beyond the elapsed read budget.
    Count=16 may therefore stop at 15 rather than extend the deadline.
    """
    check_review(review, count, interval)
    now = now or (lambda: datetime.now(BOGOTA))
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "conditions_review.json").write_text(
        json.dumps(review, indent=2) + "\n", encoding="utf-8"
    )
    own_client = client is None
    client = client or httpx.Client(
        follow_redirects=False, headers={"User-Agent": "TransMiTracker-phase1b-bounded-diagnostic"}
    )
    started, last_start = clock(), None
    captures, failures = [], []
    try:
        for number in range(count):
            target = started if last_start is None else last_start + interval
            if target - started > 840:
                failures.append({"reason": "deadline_reserve_reached"})
                break
            while clock() < target:
                sleep(min(1, target - clock()))
            if clock() - started > 840:
                failures.append({"reason": "deadline_reserve_reached"})
                break
            last_start = clock()
            requested_at = now().isoformat()
            path = directory / f"capture_{number:02}.pb"
            try:
                result = download(
                    client, ENDPOINT, path, attempts=1, max_bytes=32 * 1024**2, deadline_seconds=15
                )
                received = now()
                record = capture_record(
                    path.read_bytes(),
                    received_at=received,
                    source=ENDPOINT,
                    origin="real_network_capture",
                )
                record.update(
                    requested_at=requested_at,
                    raw_file=path.name,
                    http_status=result.status,
                    response_content_type=result.content_type,
                    last_modified=result.last_modified,
                )
                (directory / f"capture_{number:02}.json").write_text(
                    json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
                )
                captures.append(record)
                print(f"Captured {number + 1}/{count}: {record['received_at']}", flush=True)
            except (DownloadError, ValueError) as exc:
                failures.append(
                    {
                        "capture": number,
                        "error": str(exc),
                        "download": exc.result if isinstance(exc, DownloadError) else None,
                    }
                )
                break
    finally:
        if own_client:
            client.close()
        (directory / "run.json").write_text(
            json.dumps(
                {
                    "origin": "bounded_real_diagnostic",
                    "planned_captures": count,
                    "interval_seconds": interval,
                    "actual_captures": len(captures),
                    "failures": failures,
                    "elapsed_seconds": clock() - started,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return captures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    live = sub.add_parser("capture")
    live.add_argument("--review", required=True)
    live.add_argument("--count", type=int, default=3)
    live.add_argument("--interval", type=int, default=60)
    live.add_argument("--directory", default="data/phase1b/diagnostic-" + uuid4().hex)
    replay = sub.add_parser("analyze")
    replay.add_argument("captures", nargs="+")
    replay.add_argument("--catalog", default="data/catalog/official_20261112.sqlite3")
    replay.add_argument("--output", default="data/phase1b/latest-analysis.json")
    args = parser.parse_args(argv)
    try:
        if args.command == "capture":
            review = json.loads(project_path(args.review).read_text(encoding="utf-8"))
            captures = collect(
                review, project_path(args.directory), count=args.count, interval=args.interval
            )
            return 0 if len(captures) == args.count else 1
        captures = []
        for name in args.captures:
            path = project_path(name)
            record = json.loads(path.read_text(encoding="utf-8"))
            raw = (path.parent / record["raw_file"]).resolve()
            if not raw.is_relative_to(path.parent):
                raise ValueError("Raw capture path escapes its evidence directory")
            rebuilt = capture_record(
                raw.read_bytes(),
                received_at=datetime.fromisoformat(record["received_at"]),
                source=record["source"],
                origin=record["origin"],
                receipt_timestamp_verified=record.get("receipt_timestamp_verified", False),
            )
            if rebuilt["payload_sha256"] != record["payload_sha256"]:
                raise ValueError("Raw capture SHA-256 differs from its record")
            captures.append(rebuilt)
        with Catalog(project_path(args.catalog)) as catalog:
            report = TemporalAnalyzer(catalog).analyze(captures)
        output = project_path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "pairs"}, indent=2))
        return 0
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        parser.exit(2, f"Diagnostic error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
