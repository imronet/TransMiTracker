"""One-shot phase 0 diagnostics. Never falls back to fixtures silently."""

import json
import platform
from dataclasses import asdict
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from transmitracker.gtfs import FeedError
from transmitracker.gtfs.links import analyze_links
from transmitracker.gtfs.realtime import decode_realtime, is_recent_snapshot, summarize_realtime
from transmitracker.gtfs.static import read_static
from transmitracker.providers.http import DownloadError, download

ROOT = Path(__file__).resolve().parents[2]
BOGOTA = ZoneInfo("America/Bogota")


def project_path(value: str | Path) -> Path:
    path = (ROOT / value).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Paths must stay inside TransMiTracker")
    return path


def environment() -> dict:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "dependencies": {
            p: version(p) for p in ("httpx", "protobuf", "gtfs-realtime-bindings", "tzdata")
        },
    }


def offline_report() -> dict:
    fixture_dir = ROOT / "tests/fixtures"
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    reference = datetime.fromisoformat(manifest["reference_time"])
    static = read_static(fixture_dir / "synthetic_gtfs.zip")
    realtime = decode_realtime((fixture_dir / "synthetic_realtime.pb").read_bytes())
    return {
        "mode": "offline_synthetic_fixture",
        "network_requests": 0,
        "live_connection_validated": False,
        "fixture_reference_time": reference.isoformat(),
        "environment": environment(),
        "static": static.summary,
        "realtime": summarize_realtime(realtime, now=reference),
        "links": analyze_links(static, realtime, now=reference),
    }


def live_report(*, selected: list[str] | None = None, reuse_static: bool = False) -> dict:
    """Download each selected endpoint once (plus one controlled retry on errors)."""
    specs = json.loads((ROOT / "docs/endpoints.json").read_text(encoding="utf-8"))["sources"]
    if selected:
        unknown = set(selected) - {s["name"] for s in specs}
        if unknown:
            raise ValueError(f"Unknown endpoints: {sorted(unknown)}")
        specs = [s for s in specs if s["name"] in selected]
    now = datetime.now(BOGOTA)
    report = {
        "mode": "real_network_probe",
        "queried_at": now.isoformat(),
        "environment": environment(),
        "results": [],
        "id_links": {},
    }
    static, realtime_feeds = None, {}
    download_dir = ROOT / "data/probes" / now.strftime("%Y%m%dT%H%M%S%f%z")
    download_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(
        follow_redirects=True, headers={"User-Agent": "TransMiTracker-phase0/0.0.1"}
    ) as client:
        for spec in specs:
            suffix = ".zip" if spec["kind"] == "static" else ".pb"
            path = download_dir / (spec["name"] + suffix)
            entry = {
                **spec,
                "data_origin": "real_http_response",
                "network_success": False,
                "decoded": False,
                "live_connection_validated": False,
            }
            print(f"Checking {spec['name']}: {spec['url']}", flush=True)
            try:
                saved_static = (
                    sorted(
                        (ROOT / "data/probes").rglob("official_static.zip"),
                        key=lambda p: p.stat().st_mtime,
                    )
                    if reuse_static and spec["kind"] == "static"
                    else []
                )
                if saved_static:
                    path = saved_static[-1]
                    entry["data_origin"] = "previous_real_download_local_file"
                    entry["download"] = None
                else:
                    result = download(
                        client,
                        spec["url"],
                        path,
                        max_bytes=256 * 1024**2 if spec["kind"] == "static" else 32 * 1024**2,
                    )
                    entry["download"] = asdict(result)
                    entry["network_success"] = True
                entry["local_file"] = path.relative_to(ROOT).as_posix()
                if spec["kind"] == "static":
                    static = read_static(path)
                    entry["summary"] = static.summary
                else:
                    feed = decode_realtime(path.read_bytes())
                    realtime_feeds[spec["name"]] = feed
                    checked_at = datetime.now(BOGOTA)
                    summary = summarize_realtime(feed, now=checked_at)
                    entry["summary"] = summary
                    entry["live_connection_validated"] = bool(
                        entry["network_success"] and is_recent_snapshot(summary)
                    )
                entry["decoded"] = True
                entry["local_file"] = path.relative_to(ROOT).as_posix()
            except DownloadError as exc:
                entry["download"] = exc.result
                entry["error"] = str(exc)
            except (FeedError, OSError) as exc:
                entry["error"] = f"{type(exc).__name__}: {exc}"
            report["results"].append(entry)
            # Checkpoint even when the following source times out or parsing is interrupted.
            (download_dir / "checkpoint.json").write_text(
                json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            print(
                f"  network={entry['network_success']} decoded={entry['decoded']} live={entry['live_connection_validated']}",
                flush=True,
            )
    if static:
        for name, feed in realtime_feeds.items():
            report["id_links"][name] = analyze_links(static, feed, now=datetime.now(BOGOTA))
    return report
