"""Reanalyze saved real downloads, with hashes and provenance; no network."""

import json
from collections import Counter
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

from google.transit import gtfs_realtime_pb2 as pb

from transmitracker.gtfs import FeedError
from transmitracker.gtfs.links import analyze_links
from transmitracker.gtfs.realtime import decode_realtime, summarize_realtime
from transmitracker.gtfs.static import read_static

ROOT = Path(__file__).resolve().parents[1]


def main():
    original = json.loads((ROOT / "docs/LIVE_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    reference = datetime.fromisoformat(original["queried_at"])
    report = {
        "mode": "saved_real_download_analysis_no_network",
        "network_requests": 0,
        "analyzed_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
        "original_probe_started_at": reference.isoformat(),
        "files": {},
    }
    static = read_static(ROOT / "data/probes/official_static.zip")
    report["static"] = static.summary
    for entry in original["results"]:
        if not entry["network_success"]:
            continue
        name = entry["name"]
        suffix = ".zip" if entry["kind"] == "static" else ".pb"
        path = ROOT / "data/probes" / (name + suffix)
        digest = sha256(path.read_bytes()).hexdigest()
        if digest != entry["download"]["sha256"]:
            raise ValueError(f"Saved file changed since original probe: {name}")
        details = {
            "sha256": digest,
            "original_download": entry["download"],
            "hash_matches_original": True,
        }
        if entry["kind"] == "realtime":
            # Use the download's own query time; never label a saved replay as live.
            queried = datetime.fromisoformat(entry["download"]["queried_at"])
            payload = path.read_bytes()
            try:
                feed = decode_realtime(payload)
                details["strict_reader_accepted"] = True
                details["summary_at_original_query"] = summarize_realtime(feed, now=queried)
                details["links"] = analyze_links(static, feed, now=queried)
            except FeedError as exc:
                details["strict_reader_accepted"] = False
                details["strict_reader_error"] = str(exc)
                # Forensic decoding only. Does not bypass validation for application use.
                feed = pb.FeedMessage()
                feed.ParseFromString(payload)
                details["protobuf_initialized"] = feed.IsInitialized()
                ids = Counter(entity.id for entity in feed.entity)
                details["empty_entity_ids"] = ids.get("", 0)
                details["duplicate_entity_ids"] = {
                    key: count for key, count in ids.items() if count > 1
                }
                details["forensic_summary_not_accepted_for_application"] = summarize_realtime(
                    feed, now=queried
                )
        report["files"][name] = details
    output = ROOT / "docs/SAVED_FEED_ANALYSIS.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Saved real data analyzed without network:", output)
    print("Coverage:", json.dumps(static.summary["coverage_by_agency"], ensure_ascii=True))
    for name, details in report["files"].items():
        if "links" in details:
            print(name, json.dumps(details["links"]["vehicle_counts"]))
        if details.get("strict_reader_accepted") is False:
            print(
                name,
                "Rejected:",
                details["strict_reader_error"],
                "Empty IDs:",
                details["empty_entity_ids"],
                "Duplicate IDs:",
                len(details["duplicate_entity_ids"]),
            )


if __name__ == "__main__":
    main()
