"""Replay synthetic successive snapshots offline. Not a continuous collector."""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from transmitracker.research.scenarios import synthetic_snapshots
from transmitracker.research.snapshots import ingest_snapshot

ROOT = Path(__file__).resolve().parents[1]


def main():
    scenario = json.loads(
        (ROOT / "tests/fixtures/snapshot_sequence.json").read_text(encoding="utf-8")
    )
    path = (
        ROOT
        / "data/phase0_5"
        / (
            "synthetic_replay_"
            + datetime.now(ZoneInfo("America/Bogota")).strftime("%H%M%S%f")
            + ".sqlite3"
        )
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    records = []
    with sqlite3.connect(path) as connection:
        for captured, payload in synthetic_snapshots(scenario):
            result = ingest_snapshot(
                connection,
                payload,
                provider="synthetic-only",
                captured_at=captured,
                route_ids={"SYN_R1"},
            )
            records.append({"captured_at": captured.isoformat(), "result": result})
        journeys = connection.execute("SELECT COUNT(*) FROM journeys").fetchone()[0]
        observations = connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    report = {
        "origin": scenario["origin"],
        "network_requests": 0,
        "database": path.relative_to(ROOT).as_posix(),
        "snapshots": records,
        "candidate_identities": journeys,
        "observations": observations,
        "arrivals_inferred": 0,
    }
    (ROOT / "docs/PHASE0_5_SYNTHETIC_REPLAY.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
