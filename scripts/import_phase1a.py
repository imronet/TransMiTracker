"""Import the saved real static ZIP and record isolated phase 1A measurements."""

import json
from pathlib import Path

from transmitracker.catalog.importer import import_catalog

ROOT = Path(__file__).resolve().parents[1]


def main():
    result = import_catalog(
        ROOT / "data/probes/official_static.zip",
        ROOT / "data/catalog/official_20261112.sqlite3",
        source_url="https://gtfs.transmilenio.gov.co/GTFS.zip",
        progress=lambda message: print(message, flush=True),
    )
    destination = ROOT / "docs/PHASE1A_IMPORT.json"
    if destination.exists():
        destination = ROOT / "docs/PHASE1A_REIMPORT.json"
    destination.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
