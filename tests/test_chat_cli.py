import pytest

import chat


class FakeMCPClient:
    def __init__(self, error=None):
        self.error = error
        self.events = []

    def connect_all(self):
        self.events.append("connect")
        if self.error:
            raise self.error

    def disconnect_all(self):
        self.events.append("disconnect")


def test_main_disconnects_when_chat_loop_fails(monkeypatch):
    client = FakeMCPClient()
    monkeypatch.setattr(chat, "mcp_client", client)

    def fail():
        raise RuntimeError("chat failed")

    monkeypatch.setattr(chat, "run_chat_loop", fail)

    with pytest.raises(RuntimeError, match="chat failed"):
        chat.main()

    assert client.events == ["connect", "disconnect"]


def test_main_disconnects_when_startup_is_interrupted(monkeypatch):
    client = FakeMCPClient(KeyboardInterrupt())
    monkeypatch.setattr(chat, "mcp_client", client)

    with pytest.raises(KeyboardInterrupt):
        chat.main()

    assert client.events == ["connect", "disconnect"]
