"""Bounded public metadata research; no recurring feed collection or Croma calls."""

import argparse
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "official_manifest": "https://gtfs.transmilenio.gov.co/manifest.json",
    "ckan_transmilenio": "https://datosabiertos.bogota.gov.co/api/3/action/package_search?fq=organization:transmilenio&rows=1000",
    "ckan_gps": "https://datosabiertos.bogota.gov.co/api/3/action/package_search?q=GPS&rows=100",
    "ckan_travel_times": "https://datosabiertos.bogota.gov.co/api/3/action/package_search?q=tiempos%20viaje&rows=100",
    "arcgis_operational": "https://www.arcgis.com/sharing/rest/search?f=json&q=orgid%3A9unqgkQ8KCOfnzoB%20%28GPS%20OR%20posiciones%20OR%20viaje%20OR%20velocidad%20OR%20GTFS%29&num=100&sortField=modified&sortOrder=desc",
    "national_catalog": "https://api.us.socrata.com/api/catalog/v1?search_context=www.datos.gov.co&q=transmilenio&limit=100",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supplement", action="store_true")
    parser.add_argument(
        "--archive", action="store_true", help="Download one published historical static GTFS"
    )
    args = parser.parse_args()
    output = ROOT / "data/phase0_5/research"
    output.mkdir(parents=True, exist_ok=True)
    report_path = ROOT / "docs/PHASE0_5_SOURCE_RESEARCH.json"
    records = (
        json.loads(report_path.read_text(encoding="utf-8"))["results"]
        if report_path.exists()
        else []
    )
    sources = SOURCES
    if args.supplement:
        sources = {
            "arcgis_operational_page2": SOURCES["arcgis_operational"] + "&start=101",
            "arcgis_volumes_metadata": "https://services5.arcgis.com/9unqgkQ8KCOfnzoB/arcgis/rest/services/service_e89aa66a98be4ad5b990d83fb91648a7/FeatureServer?f=json",
            "observatory_travel_times": "https://observatorio.movilidadbogota.gov.co/indicadores-movilidad/tiempos-de-viajes-por-minutos",
        }
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for name, url in sources.items():
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
                    sha256=sha256(response.content).hexdigest(),
                )
                (output / f"{name}.json").write_bytes(response.content)
                if response.is_success:
                    try:
                        body = response.json()
                    except ValueError:
                        body = {}
                    if name.startswith("ckan"):
                        result = body.get("result", {})
                        record["count"] = result.get("count")
                        record["datasets"] = [
                            {
                                k: item.get(k)
                                for k in (
                                    "id",
                                    "name",
                                    "title",
                                    "notes",
                                    "license_id",
                                    "license_url",
                                    "metadata_modified",
                                    "resources",
                                )
                            }
                            for item in result.get("results", [])
                        ]
                    elif name.startswith("arcgis_operational"):
                        record["total"] = body.get("total")
                        record["next_start"] = body.get("nextStart")
                        record["items"] = [
                            {
                                k: item.get(k)
                                for k in (
                                    "id",
                                    "title",
                                    "type",
                                    "url",
                                    "description",
                                    "snippet",
                                    "licenseInfo",
                                    "created",
                                    "modified",
                                )
                            }
                            for item in body.get("results", [])
                        ]
                    elif name == "national_catalog":
                        record["result_count"] = len(body.get("results", []))
                        record["results"] = [
                            {
                                "resource": item.get("resource"),
                                "link": item.get("link"),
                                "owner": item.get("owner"),
                            }
                            for item in body.get("results", [])
                        ]
                    else:
                        record["body"] = body
            except (httpx.HTTPError, ValueError) as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            records = [r for r in records if r["name"] != name] + [record]
            print(
                name,
                "HTTP",
                record.get("status"),
                "count",
                record.get("count", record.get("total", record.get("result_count"))),
                flush=True,
            )
        if args.archive:
            # URL published by TransMilenio's ArcGIS organization, verified in phase 0.
            from dataclasses import asdict

            from transmitracker.providers.http import DownloadError, download

            url = "https://storage.googleapis.com/gtfs-estaticos/GTFS_20261027.zip"
            path = ROOT / "data/phase0_5/GTFS_20261027.zip"
            record = {
                "name": "historical_static_20261027",
                "url": url,
                "classification": "static_schedule_archive_not_operational_history",
                "provenance": "https://www.arcgis.com/home/item.html?id=6d0043cf1ba443a699bad973539a1422",
            }
            try:
                record["download"] = asdict(download(client, url, path))
                record["local_file"] = path.relative_to(ROOT).as_posix()
            except DownloadError as exc:
                record["download"] = exc.result
                record["error"] = str(exc)
            records = [r for r in records if r["name"] != record["name"]] + [record]
            print("Historical static archive:", record, flush=True)
    report = {"scope": "bounded_official_metadata_search_not_proof_of_absence", "results": records}
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
