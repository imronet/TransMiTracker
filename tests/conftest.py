import hashlib
import os
import socket
import subprocess
import sys
from pathlib import Path

import httpx
import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    """Any accidental real HTTP request fails, including in offline CLI tests."""

    def blocked(*args, **kwargs):
        raise AssertionError("Network access is forbidden in the offline test suite")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", blocked)
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture
def fixture_dir():
    return Path(__file__).parent / "fixtures"


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item, nextitem):
    """Isolate real Windows Tk cases, without skips, retries or replacing their assertions.

    Tcl in WindowsApps intermittently fails after repeated interpreter lifetimes in
    one pytest process. Each GUI case gets a fresh Python process; its own reopen
    checks and the autouse network ban still execute normally in that child.
    """
    if (
        sys.platform != "win32"
        or item.get_closest_marker("gui") is None
        or os.environ.get("TRANSMITRACKER_GUI_TEST_CHILD") == "1"
    ):
        return None
    root = Path(__file__).resolve().parents[1]
    suffix = hashlib.sha256(f"{os.getpid()}:{item.nodeid}".encode()).hexdigest()[:16]
    base = (root / ".cache/gui-workers" / suffix).resolve()
    if not base.is_relative_to(root / ".cache/gui-workers"):
        raise ValueError("Test worker directory escapes the project")
    base.parent.mkdir(parents=True, exist_ok=True)
    environment = {**os.environ, "TRANSMITRACKER_GUI_TEST_CHILD": "1", "PYTHONUTF8": "1"}

    def run_case():
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                item.nodeid,
                "-o",
                "addopts=-ra",
                "--basetemp",
                str(base),
            ],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
        )
        if completed.returncode:
            pytest.fail(
                "Real GUI subprocess failed:\n" + completed.stdout + completed.stderr, pytrace=False
            )

    item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    call = pytest.CallInfo.from_call(run_case, when="call")
    report = pytest.TestReport.from_item_and_call(item, call)
    item.ihook.pytest_runtest_logreport(report=report)
    item.ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
    return True
