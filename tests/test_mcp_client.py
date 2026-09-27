import asyncio
import concurrent.futures
from contextlib import asynccontextmanager

import pytest

from shared.clients.mcp_client import MCPConnectionError, MultiServerMCPClient


TIMEOUT_ENV = {
    "MCP_CONNECT_TIMEOUT_SECONDS": ("connect_timeout", 10),
    "MCP_OPERATION_TIMEOUT_SECONDS": ("operation_timeout", 30),
    "MCP_DISCOVERY_TTL_SECONDS": ("discovery_ttl", 60),
}


def test_constructor_is_side_effect_free_and_uses_timeout_defaults(monkeypatch):
    for variable in TIMEOUT_ENV:
        monkeypatch.delenv(variable, raising=False)

    client = MultiServerMCPClient({"hiring": {}})

    assert client._loop is None
    assert client._thread is None
    assert client.sessions == {}
    assert client.server_status == {"hiring": "disconnected"}
    for _variable, (attribute, default) in TIMEOUT_ENV.items():
        assert getattr(client, attribute) == default


@pytest.mark.parametrize("variable", TIMEOUT_ENV)
@pytest.mark.parametrize("value", ["invalid", "0", "-1", "nan", "inf"])
def test_invalid_timeout_configuration_names_only_the_variable(monkeypatch, variable, value):
    monkeypatch.setenv(variable, value)

    with pytest.raises(
        ValueError,
        match=rf"^{variable} must be a positive finite number$",
    ):
        MultiServerMCPClient()


def test_connect_all_owns_status_transitions(monkeypatch):
    client = MultiServerMCPClient({"hiring": {}, "attendance": {}})
    observed = []

    async def connect(name, _config):
        observed.append((name, client.server_status[name]))
        client.sessions[name] = object()

    monkeypatch.setattr(client, "_connect_server_async", connect)

    client.connect_all()
    try:
        assert observed == [("hiring", "connecting"), ("attendance", "connecting")]
        assert client.server_status == {
            "hiring": "connected",
            "attendance": "connected",
        }
    finally:
        client.disconnect_all()


def test_partial_startup_failure_cleans_everything(monkeypatch):
    client = MultiServerMCPClient(
        {"hiring": {}, "attendance": {}, "employee": {}}
    )
    attempts = []

    async def connect(name, _config):
        attempts.append(name)
        if name == "attendance":
            raise RuntimeError("boom")
        client.sessions[name] = object()

    monkeypatch.setattr(client, "_connect_server_async", connect)

    with pytest.raises(MCPConnectionError, match="attendance"):
        client.connect_all()

    assert attempts == ["hiring", "attendance", "employee"]
    assert client.sessions == {}
    assert client._loop is None
    assert client._thread is None
    assert client.server_status == {
        "hiring": "disconnected",
        "attendance": "failed",
        "employee": "disconnected",
    }


def test_connection_attempts_and_failure_cleanup_have_independent_timeouts(monkeypatch):
    monkeypatch.setenv("MCP_CONNECT_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("MCP_OPERATION_TIMEOUT_SECONDS", "3")
    client = MultiServerMCPClient({"hiring": {}, "attendance": {}})
    deadlines = []

    async def connect(name, _config):
        await asyncio.sleep(0)
        if name == "attendance":
            raise RuntimeError("boom")

    async def wait_for(awaitable, timeout):
        deadlines.append(timeout)
        return await awaitable

    monkeypatch.setattr(client, "_connect_server_async", connect)
    monkeypatch.setattr(asyncio, "wait_for", wait_for)

    with pytest.raises(MCPConnectionError):
        asyncio.run(client._connect_all_async())

    assert deadlines == [2, 2, 3]


def test_production_connect_method_propagates_errors(monkeypatch):
    client = MultiServerMCPClient()

    @asynccontextmanager
    async def broken_stdio(_params):
        raise RuntimeError("stdio failed")
        yield

    monkeypatch.setattr("shared.clients.mcp_client.stdio_client", broken_stdio)

    with pytest.raises(RuntimeError, match="stdio failed"):
        asyncio.run(client._connect_server_async("hiring", {}))


def test_disconnect_all_is_idempotent_and_resets_every_status(monkeypatch):
    client = MultiServerMCPClient({"hiring": {}, "attendance": {}})

    async def connect(name, _config):
        client.sessions[name] = object()

    monkeypatch.setattr(client, "_connect_server_async", connect)
    client.connect_all()
    client.server_status["attendance"] = "failed"

    client.disconnect_all()
    client.disconnect_all()

    assert client.sessions == {}
    assert client._loop is None
    assert client._thread is None
    assert client.server_status == {
        "hiring": "disconnected",
        "attendance": "disconnected",
    }


def test_disconnect_stops_loop_when_cleanup_raises(monkeypatch):
    client = MultiServerMCPClient({"hiring": {}})
    client._start_loop()
    thread = client._thread

    async def fail_cleanup(*_args, **_kwargs):
        raise RuntimeError("cleanup failed")

    monkeypatch.setattr(client, "_disconnect_all_async", fail_cleanup)

    client.disconnect_all()

    assert thread is not None and not thread.is_alive()
    assert client._loop is None
    assert client._thread is None
    assert client.server_status == {"hiring": "disconnected"}


def test_run_coroutine_cancels_future_on_bridge_timeout(monkeypatch):
    client = MultiServerMCPClient()
    client._loop = object()

    class Future:
        cancelled = False

        def result(self, timeout):
            assert timeout == 7
            raise concurrent.futures.TimeoutError

        def cancel(self):
            self.cancelled = True

    future = Future()
    monkeypatch.setattr(
        asyncio,
        "run_coroutine_threadsafe",
        lambda _coro, _loop: future,
    )

    coro = asyncio.sleep(0)
    try:
        with pytest.raises(concurrent.futures.TimeoutError):
            client._run_coroutine(coro, 7)
    finally:
        coro.close()

    assert future.cancelled


def test_configured_bridge_deadlines(monkeypatch):
    monkeypatch.setenv("MCP_CONNECT_TIMEOUT_SECONDS", "2")
    monkeypatch.setenv("MCP_OPERATION_TIMEOUT_SECONDS", "3")
    client = MultiServerMCPClient({"hiring": {}, "attendance": {}})
    deadlines = []

    def run(coro, bridge_timeout):
        deadlines.append(bridge_timeout)
        coro.close()

    monkeypatch.setattr(client, "_start_loop", lambda: None)
    monkeypatch.setattr(client, "_stop_loop", lambda: None)
    monkeypatch.setattr(client, "_run_coroutine", run)

    client.connect_all()
    client._loop = object()
    client.disconnect_all()
    client.list_tools_sync("hiring")
    client.call_tool_sync("hiring", "search_candidates", {})

    assert deadlines == [9, 4, 4, 4]
