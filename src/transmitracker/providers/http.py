"""Bounded, atomic downloads with explicit diagnostics and limited retries."""

import hashlib
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

BOGOTA = ZoneInfo("America/Bogota")


@dataclass
class DownloadResult:
    url: str
    queried_at: str
    attempts: int = 0
    status: int | None = None
    final_url: str | None = None
    content_type: str | None = None
    last_modified: str | None = None
    size_bytes: int = 0
    sha256: str | None = None


class DownloadError(Exception):
    def __init__(self, message: str, result: DownloadResult):
        super().__init__(message)
        self.result = asdict(result)


def download(
    client: httpx.Client,
    url: str,
    destination: Path,
    *,
    max_bytes: int = 256 * 1024 * 1024,
    attempts: int = 2,
    deadline_seconds: float = 180,
) -> DownloadResult:
    """GET only. At most two attempts; 429/4xx never automatically retried.

    The elapsed budget is checked between chunks/requests; an in-flight read
    can additionally consume its configured HTTP timeout. Never disables TLS.
    """
    if not 1 <= attempts <= 2 or max_bytes < 1 or deadline_seconds <= 0:
        raise ValueError("Invalid download limits")
    if httpx.URL(url).scheme != "https":
        raise ValueError("Only HTTPS downloads are supported")
    result = DownloadResult(url=url, queried_at=datetime.now(BOGOTA).isoformat())
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    started = time.monotonic()
    for attempt in range(1, attempts + 1):
        result.attempts = attempt
        result.size_bytes = 0
        transient = False
        try:
            if time.monotonic() - started >= deadline_seconds:
                raise DownloadError("Download elapsed budget exhausted", result)
            with client.stream("GET", url, timeout=httpx.Timeout(20, connect=10)) as response:
                result.status = response.status_code
                result.final_url = str(response.url)
                result.content_type = response.headers.get("content-type")
                result.last_modified = response.headers.get("last-modified")
                transient = response.status_code in {500, 502, 503, 504}
                response.raise_for_status()
                length = response.headers.get("content-length")
                if length and length.isdigit() and int(length) > max_bytes:
                    raise DownloadError("Response exceeds download size limit", result)
                digest = hashlib.sha256()
                with partial.open("wb") as target:
                    for chunk in response.iter_bytes():
                        if time.monotonic() - started >= deadline_seconds:
                            raise DownloadError("Download elapsed budget exhausted", result)
                        result.size_bytes += len(chunk)
                        if result.size_bytes > max_bytes:
                            raise DownloadError("Response exceeds download size limit", result)
                        digest.update(chunk)
                        target.write(chunk)
                if result.size_bytes == 0:
                    raise DownloadError("Empty response body", result)
                result.sha256 = digest.hexdigest()
                partial.replace(destination)
                return result
        except (httpx.HTTPError, OSError, DownloadError) as exc:
            partial.unlink(missing_ok=True)
            retryable = transient or isinstance(exc, httpx.TransportError)
            if retryable and attempt < attempts:
                time.sleep(0.5 * 2 ** (attempt - 1))
                continue
            if isinstance(exc, DownloadError):
                raise
            raise DownloadError(f"{type(exc).__name__}: {exc}", result) from exc
    raise AssertionError("Unreachable")
