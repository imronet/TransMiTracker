"""Read-only demonstration and validation against the imported real catalog."""

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from transmitracker.catalog import CatalogError
from transmitracker.catalog.common import file_hash
from transmitracker.catalog.importer import import_catalog
from transmitracker.catalog.queries import Catalog

ROOT = Path(__file__).resolve().parents[1]


def main():
    database = ROOT / "data/catalog/official_20261112.sqlite3"
    report = {
        "origin": "real_saved_static_gtfs_catalog",
        "network_requests": 0,
        "query_at": "2026-11-12T08:00:00-05:00",
    }
    when = datetime.fromisoformat(report["query_at"])
    started = time.perf_counter()
    with Catalog(database) as catalog:
        report["catalog"] = catalog.info()
        original = json.loads((ROOT / "docs/LIVE_DIAGNOSTIC.json").read_text(encoding="utf-8"))
        expected = next(
            entry["download"]["sha256"]
            for entry in original["results"]
            if entry["name"] == "official_static"
        )
        assert report["catalog"]["sha256"] == expected
        search_started = time.perf_counter()
        for query in ("Portal Norte", "Norte", "Portal"):
            origins = catalog.search_stops(query)
            for origin in origins:
                options_started = time.perf_counter()
                options = catalog.options(origin["stop_id"], when)
                options_seconds = time.perf_counter() - options_started
                if not options:
                    continue
                selection = options[0]
                destinations_started = time.perf_counter()
                destinations = catalog.destinations(
                    selection["origin_platform_id"],
                    selection["route_id"],
                    selection["direction_id"],
                    selection["pattern_id"],
                    when,
                    origin_sequence=selection["origin_sequence"],
                )
                if not destinations:
                    continue
                report["demonstration"] = {
                    "query": query,
                    "search_results": len(origins),
                    "origin": origin,
                    "option_count": len(options),
                    "selection": selection,
                    "destinations": destinations,
                    "query_timings_seconds": {
                        "search_and_selection": time.perf_counter() - search_started,
                        "options": options_seconds,
                        "destinations": time.perf_counter() - destinations_started,
                    },
                }
                break
            if "demonstration" in report:
                break
        if "demonstration" not in report:
            raise RuntimeError("No boarding option found for the documented demonstration")
        chosen = report["demonstration"]["selection"]
        failures = []
        try:
            wrong_direction = 1 if chosen["direction_id"] != 1 else 0
            catalog.destinations(
                chosen["origin_platform_id"],
                chosen["route_id"],
                wrong_direction,
                chosen["pattern_id"],
                when,
            )
        except CatalogError as exc:
            failures.append({"case": "wrong_direction", "rejected": True, "message": str(exc)})
        try:
            catalog.validate_destination(
                chosen["origin_platform_id"],
                chosen["route_id"],
                chosen["direction_id"],
                chosen["pattern_id"],
                when,
                "__NONEXISTENT_DESTINATION__",
                origin_sequence=chosen["origin_sequence"],
            )
        except CatalogError as exc:
            failures.append(
                {"case": "destination_outside_pattern", "rejected": True, "message": str(exc)}
            )
        report["rejection_checks"] = failures
        assert len(failures) == 2
        report["query_plan"] = [
            dict(r)
            for r in catalog.connection.execute(
                "EXPLAIN QUERY PLAN SELECT trip_pk,sequence FROM stop_times WHERE stop_id=? AND departure BETWEEN ? AND ?",
                (chosen["origin_platform_id"], 28800, 36000),
            )
        ]
        report["served_routes"] = catalog.connection.execute(
            "SELECT COUNT(DISTINCT route_id) FROM trips WHERE pattern_id IS NOT NULL"
        ).fetchone()[0]
        report["served_stops"] = catalog.connection.execute(
            "SELECT COUNT(DISTINCT stop_id) FROM stop_times"
        ).fetchone()[0]
        report["shape_count"] = catalog.connection.execute(
            "SELECT COUNT(*) FROM shapes"
        ).fetchone()[0]
        report["direction_counts"] = [
            dict(r)
            for r in catalog.connection.execute(
                "SELECT direction_id,COUNT(*) AS trips FROM trips GROUP BY direction_id"
            )
        ]
        report["stop_location_types"] = [
            dict(r)
            for r in catalog.connection.execute(
                "SELECT location_type,COUNT(*) AS stops FROM stops GROUP BY location_type"
            )
        ]
        report["quick_check"] = catalog.connection.execute("PRAGMA quick_check").fetchone()[0]
        report["foreign_key_check"] = [
            list(r) for r in catalog.connection.execute("PRAGMA foreign_key_check")
        ]
        report["sqlite_version"] = sqlite3.sqlite_version
    before = (file_hash(database), database.stat().st_mtime_ns)
    report["idempotent_reimport"] = import_catalog(
        ROOT / "data/probes/official_static.zip", database
    )
    assert (file_hash(database), database.stat().st_mtime_ns) == before
    report["database_unchanged_on_reimport"] = True
    report["database_bytes"] = database.stat().st_size
    report["total_verification_seconds"] = time.perf_counter() - started
    (ROOT / "docs/PHASE1A_DEMO.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in {"catalog", "demonstration"}}, indent=2
        )
    )
    print("Origin:", report["demonstration"]["origin"])
    print("Selection:", report["demonstration"]["selection"])
    print("Destinations:", len(report["demonstration"]["destinations"]))


if __name__ == "__main__":
    main()
