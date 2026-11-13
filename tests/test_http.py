import hashlib

import httpx
import pytest

from transmitracker.providers.http import DownloadError, download


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_atomic_success_and_hash(tmp_path):
    path = tmp_path / "feed.pb"
    with client_for(lambda r: httpx.Response(200, content=b"payload")) as client:
        result = download(client, "https://example.invalid/feed", path)
    assert result.sha256 == hashlib.sha256(b"payload").hexdigest()
    assert result.status == 200
    assert result.attempts == 1
    assert path.read_bytes() == b"payload"
    assert not (tmp_path / "feed.pb.part").exists()


@pytest.mark.parametrize("status", [401, 403, 404, 429])
def test_permanent_errors_and_throttling_not_retried(tmp_path, status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Retry-After": "60"})

    with client_for(handler) as client, pytest.raises(DownloadError) as error:
        download(client, "https://example.invalid/feed", tmp_path / "feed.pb")
    assert error.value.result["status"] == status
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["timeout", "dns", "server"])
def test_transient_retry_is_bounded(tmp_path, monkeypatch, failure):
    monkeypatch.setattr("transmitracker.providers.http.time.sleep", lambda _: None)
    calls = []

    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("simulated timeout", request=request)
        if failure == "dns":
            raise httpx.ConnectError("simulated DNS error", request=request)
        return httpx.Response(503)

    with client_for(handler) as client, pytest.raises(DownloadError) as error:
        download(client, "https://example.invalid/feed", tmp_path / "feed.pb")
    assert error.value.result["attempts"] == 2
    assert len(calls) == 2


def test_retry_recovers(tmp_path, monkeypatch):
    monkeypatch.setattr("transmitracker.providers.http.time.sleep", lambda _: None)
    responses = iter([httpx.Response(502), httpx.Response(200, content=b"ok")])
    with client_for(lambda r: next(responses)) as client:
        result = download(client, "https://example.invalid/feed", tmp_path / "feed.pb")
    assert result.attempts == 2


@pytest.mark.parametrize(
    "body,headers", [(b"", {}), (b"12345", {}), (b"12345", {"Content-Length": "5"})]
)
def test_empty_or_oversized_does_not_overwrite_previous_file(tmp_path, body, headers):
    path = tmp_path / "feed.pb"
    path.write_bytes(b"previous")
    with client_for(lambda r: httpx.Response(200, content=body, headers=headers)) as client:
        with pytest.raises(DownloadError):
            download(client, "https://example.invalid/feed", path, max_bytes=3)
    assert path.read_bytes() == b"previous"
    assert not path.with_name("feed.pb.part").exists()


def test_elapsed_deadline(tmp_path, monkeypatch):
    ticks = iter([0.0, 2.0])
    monkeypatch.setattr("transmitracker.providers.http.time.monotonic", lambda: next(ticks))
    with client_for(lambda r: httpx.Response(200, content=b"ok")) as client:
        with pytest.raises(DownloadError, match="budget"):
            download(
                client, "https://example.invalid/feed", tmp_path / "feed.pb", deadline_seconds=1
            )


def test_insecure_url_rejected(tmp_path):
    with client_for(lambda r: httpx.Response(200)) as client:
        with pytest.raises(ValueError, match="HTTPS"):
            download(client, "http://example.invalid/feed", tmp_path / "feed.pb")
