import asyncio
import concurrent.futures
import importlib
import os
import time
from contextlib import asynccontextmanager

import pytest

from shared.clients.mcp_client import MCPConnectionError, MultiServerMCPClient


class FakeTool:
    def __init__(self, name="tool", description="description", input_schema=None):
        self.name = name
        self.description = description
        self.inputSchema = {} if input_schema is None else input_schema


class FakeTools:
    def __init__(self, tools, next_cursor=None):
        self.tools = tools
        self.next_cursor = next_cursor


class FakeCallResult:
    def __init__(self, *, is_error=False, content=None):
        self.is_error = is_error
        self.content = content or []


class FakeSession:
    def __init__(self, pages=None, call_result=None):
        self.pages = list(pages or [])
        self.call_result = call_result or FakeCallResult()
        self.list_calls = []
        self.call_calls = []

    async def list_tools(self, *, params=None):
        cursor = getattr(params, "cursor", None)
        self.list_calls.append(cursor)
        response = self.pages.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def call_tool(self, name, arguments):
        self.call_calls.append((name, arguments))
        if isinstance(self.call_result, BaseException):
            raise self.call_result
        return self.call_result


def connected_client(session, monkeypatch=None, **environment):
    if monkeypatch:
        for name, value in environment.items():
            monkeypatch.setenv(name, str(value))
    client = MultiServerMCPClient({"hiring": {}})
    client.sessions["hiring"] = session
    client.server_status["hiring"] = "connected"
    return client


TIMEOUT_ENV = {
    "MCP_CONNECT_TIMEOUT_SECONDS": ("connect_timeout", 10),
    "MCP_OPERATION_TIMEOUT_SECONDS": ("operation_timeout", 30),
    "MCP_DISCOVERY_TTL_SECONDS": ("discovery_ttl", 60),
}


def test_agent_setup_import_does_not_connect(monkeypatch):
    calls = []
    original_environment = dict(os.environ)
    monkeypatch.setattr(
        MultiServerMCPClient,
        "connect_all",
        lambda self: calls.append(self),
    )

    import apps.chatbot.agent_setup as agent_setup

    original_state = {
        name: getattr(agent_setup, name)
        for name in ("mcp_client", "llm_provider", "root_agent")
    }
    try:
        importlib.reload(agent_setup)
    finally:
        for name, value in original_state.items():
            setattr(agent_setup, name, value)
        os.environ.clear()
        os.environ.update(original_environment)
    assert calls == []


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


@pytest.mark.parametrize(
    "failure_type", [concurrent.futures.TimeoutError, KeyboardInterrupt]
)
def test_outer_startup_failure_cleans_partial_resources_before_stopping_loop(
    monkeypatch, failure_type
):
    client = MultiServerMCPClient({"hiring": {}})
    original_run = client._run_coroutine
    cleanup_called = []
    cleanup_deadlines = []
    captured_thread = None

    async def record_cleanup():
        cleanup_called.append(True)

    client._exit_stack.push_async_callback(record_cleanup)

    def run(coro, bridge_timeout):
        nonlocal captured_thread
        if captured_thread is None:
            captured_thread = client._thread
            client.sessions["hiring"] = object()
            client.server_status["hiring"] = "connected"
            coro.close()
            raise failure_type
        cleanup_deadlines.append(bridge_timeout)
        return original_run(coro, bridge_timeout)

    monkeypatch.setattr(client, "_run_coroutine", run)

    with pytest.raises(failure_type):
        client.connect_all()

    assert cleanup_called == [True]
    assert cleanup_deadlines == [client.operation_timeout + 1]
    assert client.sessions == {}
    assert client.server_status == {"hiring": "disconnected"}
    assert captured_thread is not None and not captured_thread.is_alive()
    assert client._loop is None
    assert client._thread is None


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


def test_disconnect_internally_times_out_and_cancels_hanging_cleanup(monkeypatch):
    monkeypatch.setenv("MCP_OPERATION_TIMEOUT_SECONDS", "0.01")
    client = MultiServerMCPClient({"hiring": {}})
    client._start_loop()
    thread = client._thread
    client.sessions["hiring"] = object()
    client.server_status["hiring"] = "connected"
    finalized = []

    async def hang_until_cancelled():
        try:
            await asyncio.Future()
        finally:
            finalized.append(True)

    client._exit_stack.push_async_callback(hang_until_cancelled)

    started = time.monotonic()
    client.disconnect_all()
    elapsed = time.monotonic() - started

    assert elapsed < 0.5
    assert finalized == [True]
    assert client.sessions == {}
    assert client.server_status == {"hiring": "disconnected"}
    assert thread is not None and not thread.is_alive()
    assert client._loop is None
    assert client._thread is None


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

    def wait_for(awaitable, *, timeout):
        awaitable.close()
        return asyncio.sleep(0)

    monkeypatch.setattr(client, "_start_loop", lambda: None)
    monkeypatch.setattr(client, "_stop_loop", lambda: None)
    monkeypatch.setattr(client, "_run_coroutine", run)
    monkeypatch.setattr(asyncio, "wait_for", wait_for)

    client.connect_all()
    client._loop = object()
    client.disconnect_all()
    client.list_tools_sync("hiring")
    client.call_tool_sync("hiring", "search_candidates", {})

    assert deadlines == [9, 4, 4, 4]


def test_list_tools_follows_pages_and_caches():
    async def exercise():
        session = FakeSession([
            FakeTools([FakeTool("one")], next_cursor="page-2"),
            FakeTools([FakeTool("two")]),
        ])
        client = connected_client(session)

        assert [tool.name for tool in await client.list_tools("hiring")] == [
            "one",
            "two",
        ]
        assert [tool.name for tool in await client.list_tools("hiring")] == [
            "one",
            "two",
        ]
        assert session.list_calls == [None, "page-2"]

    asyncio.run(exercise())


def test_list_tools_rejects_repeated_cursor():
    async def exercise():
        session = FakeSession([
            FakeTools([FakeTool("one")], next_cursor="same"),
            FakeTools([FakeTool("two")], next_cursor="same"),
        ])
        client = connected_client(session)

        with pytest.raises(MCPConnectionError, match="Repeated discovery cursor"):
            await client.list_tools("hiring")

        assert session.list_calls == [None, "same"]
        assert client.server_status["hiring"] == "failed"

    asyncio.run(exercise())


def test_list_tools_uses_one_deadline_for_all_pages(monkeypatch):
    async def exercise():
        cancelled = False

        class SlowSession:
            calls = 0

            async def list_tools(self, *, params=None):
                nonlocal cancelled
                try:
                    await asyncio.sleep(0.03)
                except asyncio.CancelledError:
                    cancelled = True
                    raise
                self.calls += 1
                return FakeTools(
                    [FakeTool(str(self.calls))], next_cursor=str(self.calls)
                )

        session = SlowSession()
        client = connected_client(
            session,
            monkeypatch,
            MCP_OPERATION_TIMEOUT_SECONDS=0.05,
        )

        with pytest.raises(MCPConnectionError, match="timed out"):
            await client.list_tools("hiring")

        assert session.calls == 1
        assert cancelled

    asyncio.run(exercise())


def test_list_tools_requires_connected_server():
    client = MultiServerMCPClient({"hiring": {}})

    with pytest.raises(MCPConnectionError, match="hiring"):
        asyncio.run(client.list_tools("hiring"))


def test_list_tools_force_refreshes_cached_discovery():
    async def exercise():
        session = FakeSession([
            FakeTools([FakeTool("one")]),
            FakeTools([FakeTool("two")]),
        ])
        client = connected_client(session)

        assert [tool.name for tool in await client.list_tools("hiring")] == ["one"]
        assert [
            tool.name for tool in await client.list_tools("hiring", force=True)
        ] == ["two"]
        assert session.list_calls == [None, None]

    asyncio.run(exercise())


def test_failed_refresh_preserves_but_does_not_return_stale_cache():
    async def exercise():
        session = FakeSession([
            FakeTools([FakeTool("one")]),
            RuntimeError("refresh failed"),
        ])
        client = connected_client(session)

        cached = await client.list_tools("hiring")
        with pytest.raises(MCPConnectionError, match="hiring"):
            await client.list_tools("hiring", force=True)

        assert client.server_status["hiring"] == "failed"
        assert await client.list_tools("hiring") == cached
        assert session.list_calls == [None, None]

    asyncio.run(exercise())


def test_expired_discovery_cache_is_refreshed(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("shared.cache.in_memory_cache.time.time", lambda: clock[0])

    async def exercise():
        session = FakeSession([
            FakeTools([FakeTool("one")]),
            FakeTools([FakeTool("two")]),
        ])
        client = connected_client(
            session,
            monkeypatch,
            MCP_DISCOVERY_TTL_SECONDS=5,
        )

        assert [tool.name for tool in await client.list_tools("hiring")] == ["one"]
        clock[0] += 6
        assert [tool.name for tool in await client.list_tools("hiring")] == ["two"]
        assert session.list_calls == [None, None]

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "tool",
    [
        FakeTool(""),
        FakeTool(1),
        FakeTool(description=1),
        FakeTool(input_schema=[]),
    ],
)
def test_invalid_tool_definition_is_rejected_and_not_cached(tool):
    async def exercise():
        session = FakeSession([
            FakeTools([tool]),
            FakeTools([FakeTool("valid")]),
        ])
        client = connected_client(session)

        with pytest.raises(MCPConnectionError, match="hiring"):
            await client.list_tools("hiring")

        assert [tool.name for tool in await client.list_tools("hiring")] == [
            "valid"
        ]
        assert session.list_calls == [None, None]

    asyncio.run(exercise())


def test_list_tools_timeout_marks_server_failed(monkeypatch):
    async def exercise():
        session = FakeSession()
        cancelled = False

        async def hang(*, params=None):
            nonlocal cancelled
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                cancelled = True
                raise

        session.list_tools = hang
        client = connected_client(
            session,
            monkeypatch,
            MCP_OPERATION_TIMEOUT_SECONDS=0.01,
        )

        with pytest.raises(MCPConnectionError, match="hiring"):
            await client.list_tools("hiring")
        assert cancelled
        assert client.server_status["hiring"] == "failed"

    asyncio.run(exercise())


def test_call_tool_timeout_returns_failure_and_marks_server_failed(monkeypatch):
    async def exercise():
        session = FakeSession()

        async def hang(_name, _arguments):
            await asyncio.Future()

        session.call_tool = hang
        client = connected_client(
            session,
            monkeypatch,
            MCP_OPERATION_TIMEOUT_SECONDS=0.01,
        )

        result = await client.call_tool("hiring", "search_candidates", {})

        assert not result.success
        assert result.error == "MCP operation timed out: hiring.search_candidates"
        assert result.metadata == {
            "server": "hiring",
            "tool": "search_candidates",
        }
        assert client.server_status["hiring"] == "failed"

    asyncio.run(exercise())


def test_tool_level_error_leaves_server_connected():
    async def exercise():
        class Text:
            type = "text"
            text = '{"success": true, "data": {"value": 1}}'

        client = connected_client(
            FakeSession(call_result=FakeCallResult(is_error=True, content=[Text()]))
        )

        result = await client.call_tool("hiring", "search_candidates", {})

        assert not result.success
        assert result.error == Text.text
        assert client.server_status["hiring"] == "connected"

    asyncio.run(exercise())


def test_sync_operation_timeout_contracts(monkeypatch):
    client = MultiServerMCPClient({"hiring": {}})
    client._loop = object()
    futures = []

    class Future:
        def __init__(self):
            self.cancelled = False
            self.timeout = None

        def result(self, timeout):
            self.timeout = timeout
            raise concurrent.futures.TimeoutError

        def cancel(self):
            self.cancelled = True

    def submit(coro, _loop):
        coro.close()
        future = Future()
        futures.append(future)
        return future

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", submit)

    with pytest.raises(MCPConnectionError, match="hiring"):
        client.list_tools_sync("hiring")
    result = client.call_tool_sync("hiring", "search_candidates", {})

    assert [future.timeout for future in futures] == [
        client.operation_timeout + 1,
        client.operation_timeout + 1,
    ]
    assert all(future.cancelled for future in futures)
    assert not result.success
    assert result.error == "MCP operation timed out: hiring.search_candidates"
    assert result.metadata == {
        "server": "hiring",
        "tool": "search_candidates",
    }
    assert client.server_status["hiring"] == "failed"
