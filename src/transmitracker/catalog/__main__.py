"""Local GTFS catalog CLI. No network access or realtime operations."""

import argparse
import json
import sqlite3
from datetime import datetime

from transmitracker.catalog import CatalogError
from transmitracker.catalog.importer import import_catalog
from transmitracker.catalog.queries import Catalog
from transmitracker.diagnostics import project_path


def choose(items, label, automatic):
    if not items:
        raise CatalogError(f"No available {label}")
    for number, item in enumerate(items, 1):
        print(f"{number}. {json.dumps(item, ensure_ascii=False)}")
    selection = 1 if automatic else int(input(f"Select {label} [1-{len(items)}]: "))
    if not 1 <= selection <= len(items):
        raise CatalogError("Invalid selection")
    return items[selection - 1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="data/catalog/official_20261112.sqlite3")
    sub = parser.add_subparsers(dest="command", required=True)
    load = sub.add_parser("import")
    load.add_argument("zip")
    load.add_argument("--source-url")
    load.add_argument("--batch-size", type=int, default=10000)
    sub.add_parser("info")
    search = sub.add_parser("search")
    search.add_argument("query")
    options = sub.add_parser("options")
    options.add_argument("origin")
    destinations = sub.add_parser("destinations")
    destinations.add_argument("origin")
    destinations.add_argument("route")
    destinations.add_argument("pattern")
    destinations.add_argument("--direction", choices=("0", "1", "unknown"), required=True)
    destinations.add_argument("--origin-sequence", type=int)
    demo = sub.add_parser("demo")
    demo.add_argument("query")
    demo.add_argument(
        "--auto", action="store_true", help="Select first available origin and pattern"
    )
    for command in (options, destinations, demo):
        command.add_argument(
            "--when", required=True, help="ISO 8601 with timezone, e.g. 2026-11-12T08:00:00-05:00"
        )
        command.add_argument("--window-minutes", type=int, default=120)
    args = parser.parse_args(argv)
    try:
        database = project_path(args.db)
        if args.command == "import":
            result = import_catalog(
                project_path(args.zip),
                database,
                source_url=args.source_url,
                batch_size=args.batch_size,
                progress=print,
            )
        else:
            with Catalog(database) as catalog:
                if args.command == "info":
                    result = catalog.info()
                elif args.command == "search":
                    result = catalog.search_stops(args.query)
                else:
                    when = datetime.fromisoformat(args.when)
                    if args.command == "options":
                        result = catalog.options(
                            args.origin, when, window_minutes=args.window_minutes
                        )
                    elif args.command == "destinations":
                        direction = None if args.direction == "unknown" else int(args.direction)
                        result = catalog.destinations(
                            args.origin,
                            args.route,
                            direction,
                            args.pattern,
                            when,
                            origin_sequence=args.origin_sequence,
                            window_minutes=args.window_minutes,
                        )
                    else:
                        origin = choose(catalog.search_stops(args.query), "origin", args.auto)
                        option = choose(
                            catalog.options(
                                origin["stop_id"], when, window_minutes=args.window_minutes
                            ),
                            "route/pattern",
                            args.auto,
                        )
                        result = {
                            "origin": origin,
                            "selection": option,
                            "destinations": catalog.destinations(
                                option["origin_platform_id"],
                                option["route_id"],
                                option["direction_id"],
                                option["pattern_id"],
                                when,
                                origin_sequence=option["origin_sequence"],
                                window_minutes=args.window_minutes,
                            ),
                        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (CatalogError, sqlite3.Error, OSError, ValueError, EOFError) as exc:
        parser.exit(2, f"Catalog error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
