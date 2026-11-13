import hashlib
import json
from pathlib import Path

import httpx
import pytest

import transmitracker.diagnostics as diagnostics
from transmitracker.__main__ import main
from transmitracker.diagnostics import offline_report, project_path


def test_fixture_provenance_and_hashes(fixture_dir):
    manifest = json.loads((fixture_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["origin"] == "synthetic_hand_authored_not_an_api_response"
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((fixture_dir / name).read_bytes()).hexdigest() == digest


def test_offline_report_never_claims_real_connection():
    report = offline_report()
    assert report["mode"] == "offline_synthetic_fixture"
    assert report["network_requests"] == 0
    assert report["live_connection_validated"] is False
    assert report["links"]["vehicle_counts"]["trip_id_matched"] == 1


def test_cli_offline_default(capsys):
    assert main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "offline_synthetic_fixture"


def test_paths_cannot_escape_project():
    with pytest.raises(ValueError, match="inside"):
        project_path(Path("..") / "outside.json")


def test_live_flags_require_explicit_live():
    with pytest.raises(SystemExit) as error:
        main(["--reuse-static"])
    assert error.value.code == 2


def test_probe_orchestration_with_mock_http_only(tmp_path, fixture_dir, monkeypatch):
    """Exercise the live code path with fake transport; this is not live evidence."""
    (tmp_path / "docs").mkdir()
    sources = [
        {"name": "official_static", "kind": "static", "url": "https://example.invalid/static"},
        {"name": "positions", "kind": "realtime", "url": "https://example.invalid/positions"},
        {"name": "bad", "kind": "realtime", "url": "https://example.invalid/bad"},
    ]
    (tmp_path / "docs/endpoints.json").write_text(
        json.dumps({"sources": sources}), encoding="utf-8"
    )
    client_class = httpx.Client
    requests = []

    def handler(request):
        requests.append(request.url.path)
        payload = {
            "/static": (fixture_dir / "synthetic_gtfs.zip").read_bytes(),
            "/positions": (fixture_dir / "synthetic_realtime.pb").read_bytes(),
            "/bad": b"<html>maintenance</html>",
        }[request.url.path]
        return httpx.Response(200, content=payload)

    monkeypatch.setattr(diagnostics, "ROOT", tmp_path)
    monkeypatch.setattr(
        diagnostics.httpx,
        "Client",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )
    report = diagnostics.live_report()
    assert [e["decoded"] for e in report["results"]] == [True, True, False]
    assert report["id_links"]["positions"]["vehicle_counts"]["trip_id_matched"] == 1
    first_static = report["results"][0]["local_file"]
    assert (tmp_path / first_static).exists()
    assert len(list((tmp_path / "data/probes").glob("*/checkpoint.json"))) == 1
    requests.clear()
    reused = diagnostics.live_report(selected=["official_static"], reuse_static=True)
    assert not requests
    assert reused["results"][0]["network_success"] is False
    assert reused["results"][0]["data_origin"] == "previous_real_download_local_file"
    assert reused["results"][0]["local_file"] == first_static
