"""Read public provider conditions once; never polls vehicle feeds."""

import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "portal": "https://gtfs.transmilenio.gov.co/",
    "robots": "https://gtfs.transmilenio.gov.co/robots.txt",
    "manifest": "https://gtfs.transmilenio.gov.co/manifest.json",
    "terms": "https://www.transmilenio.gov.co/comunicaciones/publicaciones/2025/terminos-y-condiciones-en-el-sitio-web-de-transmilenio",
}


def main():
    directory = ROOT / "data/phase1b/conditions"
    directory.mkdir(parents=True, exist_ok=True)
    report = {"reviewed_at": datetime.now(ZoneInfo("America/Bogota")).isoformat(), "sources": []}
    with httpx.Client(timeout=20, follow_redirects=True) as client:
        for name, url in SOURCES.items():
            record = {"name": name, "url": url}
            try:
                response = client.get(url)
                record.update(
                    status=response.status_code,
                    final_url=str(response.url),
                    sha256=sha256(response.content).hexdigest(),
                    bytes=len(response.content),
                )
                (directory / f"{name}.txt").write_bytes(response.content)
            except httpx.HTTPError as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            report["sources"].append(record)
            print(record, flush=True)
    (ROOT / "docs/PHASE1B_PROVIDER_REVIEW.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
