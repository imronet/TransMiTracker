"""Console entry point for phase 0 only; offline by default."""

import argparse
import json

from transmitracker.diagnostics import live_report, offline_report, project_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline", action="store_true", help="Use explicitly synthetic fixtures (default)"
    )
    mode.add_argument(
        "--live", action="store_true", help="One-shot real downloads from official endpoints"
    )
    parser.add_argument(
        "--only", nargs="+", help="Endpoint names from docs/endpoints.json (live only)"
    )
    parser.add_argument(
        "--reuse-static",
        action="store_true",
        help="Use a previously downloaded static ZIP; marks it as local evidence",
    )
    parser.add_argument("--output", help="Write JSON inside this project")
    args = parser.parse_args(argv)
    if (args.only or args.reuse_static) and not args.live:
        parser.error("--only and --reuse-static require --live")
    try:
        output = project_path(args.output) if args.output else None
        report = (
            live_report(selected=args.only, reuse_static=args.reuse_static)
            if args.live
            else offline_report()
        )
        text = json.dumps(report, indent=2, ensure_ascii=False)
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(text + "\n", encoding="utf-8")
        print(text)
        if args.live and any(not entry["decoded"] for entry in report["results"]):
            return 1
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Diagnostic error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
