"""Build deterministic synthetic fixtures. No network or real API data."""

import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from google.protobuf import text_format
from google.transit import gtfs_realtime_pb2

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures"


def main():
    with ZipFile(FIXTURES / "synthetic_gtfs.zip", "w") as archive:
        for path in sorted((FIXTURES / "gtfs").glob("*.txt")):
            info = ZipInfo(path.name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(
                info, path.read_text(encoding="utf-8").replace("\r\n", "\n").encode("utf-8")
            )
    message = gtfs_realtime_pb2.FeedMessage()
    text_format.Parse(
        (FIXTURES / "synthetic_realtime.textproto").read_text(encoding="utf-8"), message
    )
    (FIXTURES / "synthetic_realtime.pb").write_bytes(message.SerializeToString(deterministic=True))
    manifest = {
        "origin": "synthetic_hand_authored_not_an_api_response",
        "reference_time": "2026-11-12T07:00:00-05:00",
        "generator": "scripts/build_fixtures.py",
        "files": {
            name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
            for name in ("synthetic_gtfs.zip", "synthetic_realtime.pb")
        },
    }
    (FIXTURES / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print("Synthetic fixtures built; no network access.")


if __name__ == "__main__":
    main()
