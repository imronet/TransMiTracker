import hashlib
import re
import unicodedata
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from transmitracker.catalog import CatalogError

BOGOTA = ZoneInfo("America/Bogota")


@lru_cache(maxsize=200_000)
def gtfs_seconds(value: str) -> int | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d+):([0-5]\d):([0-5]\d)", value)
    if not match:
        raise CatalogError(f"Invalid GTFS time: {value!r}")
    hours, minutes, seconds = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds


def normalized(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)
    )


def file_hash(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CatalogError("A timezone-aware date/time is required")
    return value.astimezone(BOGOTA)
