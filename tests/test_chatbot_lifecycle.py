import asyncio

import pytest
from fastapi.testclient import TestClient

from apps.chatbot.main import app, lifespan


class FakeMCPClient:
    def __init__(self, error=None):
        self.error = error
        self.events = []
        self.server_status = {"hiring": "disconnected"}

    def connect_all(self):
        self.events.append("connect")
        if self.error:
            raise self.error

    def disconnect_all(self):
        self.events.append("disconnect")


def test_lifespan_owns_mcp_connection(monkeypatch):
    client = FakeMCPClient()
    monkeypatch.setattr("apps.chatbot.main.mcp_client", client)

    with TestClient(app):
        assert client.events == ["connect"]

    assert client.events == ["connect", "disconnect"]


def test_lifespan_propagates_connection_failure(monkeypatch):
    client = FakeMCPClient(RuntimeError("startup failed"))
    monkeypatch.setattr("apps.chatbot.main.mcp_client", client)

    with pytest.raises(RuntimeError, match="startup failed"):
        with TestClient(app):
            pass

    assert client.events == ["connect", "disconnect"]


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, asyncio.CancelledError])
def test_lifespan_disconnects_when_startup_is_interrupted(monkeypatch, error_type):
    client = FakeMCPClient(error_type())
    monkeypatch.setattr("apps.chatbot.main.mcp_client", client)

    async def start():
        async with lifespan(app):
            pass

    with pytest.raises(error_type):
        asyncio.run(start())

    assert client.events == ["connect", "disconnect"]
