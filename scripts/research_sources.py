"""Consult only public documentation/metadata; never Croma's paid operations."""

import argparse
import json
import sys
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "official_index": "https://gtfs.transmilenio.gov.co/",
    "official_script": "https://gtfs.transmilenio.gov.co/scripts.js",
    "official_manifest": "https://gtfs.transmilenio.gov.co/manifest.json",
    "legacy_index": "https://gis.transmilenio.gov.co/gtfs/",
    "static_catalog": "https://datosabiertos.bogota.gov.co/api/3/action/package_show?id=especificacion-gtfs-general-transport-feed-specification-sitp",
    "static_arcgis": "https://www.arcgis.com/sharing/rest/content/items/23ca762178a94b23a5e227ce60e2b08e?f=json",
    "static_search": "https://www.arcgis.com/sharing/rest/search?f=json&q=orgid%3A9unqgkQ8KCOfnzoB%20GTFS&num=100&sortField=modified&sortOrder=desc",
    "croma_original": "https://docs.usecroma.com/es/guides/colombia/transmilenio",
    "croma_guide": "https://docs.usecroma.com/guides/colombia/transmilenio.md",
    "croma_spanish": "https://docs.usecroma.com/es/guides/colombia/transmilenio.md",
    "croma_auth": "https://docs.usecroma.com/authentication.md",
    "croma_credits": "https://docs.usecroma.com/credits.md",
    "croma_limits": "https://docs.usecroma.com/rate-limits.md",
    "croma_openapi": "https://usecroma.com/openapi.json",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=SOURCES)
    args = parser.parse_args()
    output = ROOT / "data/research"
    output.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / "docs/SOURCE_RESEARCH.json"
    records = (
        json.loads(report_path.read_text(encoding="utf-8"))["results"]
        if report_path.exists()
        else []
    )
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for name, url in SOURCES.items():
            if args.only and name not in args.only:
                continue
            record = {
                "name": name,
                "url": url,
                "queried_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(),
            }
            try:
                response = client.get(url)
                record.update(
                    status=response.status_code,
                    final_url=str(response.url),
                    bytes=len(response.content),
                    content_type=response.headers.get("content-type"),
                    sha256=sha256(response.content).hexdigest(),
                )
                (output / f"{name}.txt").write_bytes(response.content)
                if name == "static_catalog" and response.is_success:
                    result = response.json().get("result", {})
                    record["resources"] = [
                        {"name": r.get("name"), "url": r.get("url"), "format": r.get("format")}
                        for r in result.get("resources", [])
                    ]
                if name == "static_arcgis" and response.is_success:
                    record["metadata"] = response.json()
                if name == "static_search" and response.is_success:
                    record["items"] = [
                        {k: r.get(k) for k in ("id", "title", "url", "modified")}
                        for r in response.json().get("results", [])
                    ]
                if name == "croma_openapi" and response.is_success:
                    record["transmilenio_operations"] = {
                        p: {
                            "operation_id": v["post"].get("operationId"),
                            "served_from": v["post"].get("x-served-from", "live"),
                            "security": v["post"].get("security"),
                        }
                        for p, v in response.json().get("paths", {}).items()
                        if "transmilenio" in p
                    }
            except (httpx.HTTPError, ValueError) as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            records = [r for r in records if r["name"] != name] + [record]
            print(json.dumps(record, ensure_ascii=True), flush=True)
    report_path.write_text(
        json.dumps({"python": sys.version, "results": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
