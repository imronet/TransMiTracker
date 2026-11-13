import socket
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
