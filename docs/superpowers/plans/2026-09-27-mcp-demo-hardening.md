# MCP Demo Hardening Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing three-server stdio MCP demo start, report readiness, execute, cache discovery, and shut down deterministically.

**Architecture:** Keep `MultiServerMCPClient` as the only MCP client and make its construction side-effect free. FastAPI lifespan and the CLI own connection lifetime; the existing in-memory cache stores successful tool discovery only, while all tool calls remain live.

**Tech Stack:** Python 3, MCP Python SDK 2.x, FastAPI lifespan, `asyncio`, `threading`, pytest.

---

## File Map

- Modify `shared/clients/mcp_client.py`: lifecycle, status, timeout, pagination, discovery cache, and sync bridge.
- Create `tests/test_mcp_client.py`: focused client lifecycle/cache/timeout tests using fake sessions.
- Modify `apps/chatbot/agent_setup.py`: build the configured client without connecting at import.
- Modify `apps/chatbot/main.py`: FastAPI lifespan ownership and readiness endpoint.
- Modify `chat.py`: CLI connection ownership with guaranteed cleanup.
- Modify `tests/test_chatbot_api.py`: lifespan-aware client fixture and readiness assertions.
- Modify `tests/test_settings_api.py`: lifespan-aware fixture and exact `.env`/environment restoration.
- Create `tests/test_chatbot_lifecycle.py`: isolated FastAPI ownership tests with a fake MCP client.
- Create `tests/test_chat_cli.py`: isolated CLI cleanup test.
- Modify `shared/logger/__init__.py`: stop duplicate propagated records.
- Create `tests/test_logger.py`: one-record regression check.
- Create `scripts/smoke_mcp_demo.py`: deterministic three-domain, real-stdio smoke check.
- Create `tests/test_mcp_stdio_integration.py`: real discovery/call verification for all three servers.
- Modify `.env.example`, `apps/chatbot/routers/settings.py`, `requirements.txt`, `README.md`; create `constraints.txt`: expose verified settings and installation/demo commands.

## Chunk 1: MCP Client Core

### Task 1: Side-effect-free lifecycle, status, and timeout behavior

**Files:**
- Modify: `shared/clients/mcp_client.py`
- Create: `tests/test_mcp_client.py`

- [ ] **Step 1: Write failing lifecycle tests**

Add tests that construct a client and assert `_loop is None`, `_thread is None`, no sessions, and all configured states are `disconnected`. Verify absent environment variables produce `connect_timeout=10`, `operation_timeout=30`, and `discovery_ttl=60`; parameterize invalid strings, zero, negatives, `nan`, and `inf` for every variable and assert `ValueError` names only the variable. Patch `_connect_server_async` with an async fake that only records and returns/raises—the production orchestration must own every `connecting → connected/failed` transition. The failure test uses three servers with the middle one failing, records that all three were attempted in configuration order, and asserts one aggregate `MCPConnectionError`, no sessions, no live loop/thread, plus exact final states `disconnected/failed/disconnected`. Add an idempotent double-disconnect test, a public-disconnect assertion that every state becomes `disconnected`, and a cleanup-exception case proving the loop still stops and joins.

```python
def test_constructor_starts_no_background_thread():
    client = MultiServerMCPClient({"hiring": {}})
    assert client._loop is None
    assert client._thread is None
    assert client.server_status == {"hiring": "disconnected"}


def test_partial_startup_failure_cleans_everything(monkeypatch):
    client = MultiServerMCPClient({"hiring": {}, "attendance": {}, "employee": {}})
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
    assert client._thread is None
    assert client.server_status == {
        "hiring": "disconnected",
        "attendance": "failed",
        "employee": "disconnected",
    }
```

- [ ] **Step 2: Run lifecycle tests and verify failure**

Run: `python -m pytest tests/test_mcp_client.py -v`

Expected: FAIL because construction currently starts a loop thread and no status/error contract exists.

- [ ] **Step 3: Implement the minimum lifecycle contract**

In `shared/clients/mcp_client.py`, add `MCPConnectionError(RuntimeError)`, constructor values sourced from `MCP_CONNECT_TIMEOUT_SECONDS`, `MCP_OPERATION_TIMEOUT_SECONDS`, and `MCP_DISCOVERY_TTL_SECONDS` with defaults `10`, `30`, and `60`, `server_status`, and lazy `_start_loop()`/`_stop_loop()`. Validate numbers with one helper:

```python
def _positive_number(value: Any, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return number
```

Remove `_connect_server_async()`'s catch-and-`False` behavior: it either installs a session and returns normally or propagates the connection exception. `connect_all()` starts the loop and, for each configured server, sets `connecting`, awaits `_connect_server_async` through a per-server `asyncio.wait_for(..., connect_timeout)`, then sets `connected` or `failed`. Test both a raised failure and the production method contract; no false return value is accepted. It collects failures and still attempts later servers. On any failure it calls internal async cleanup with `preserve_failed=True`, stops/joins the loop, resets formerly connected states to `disconnected`, preserves failed states for diagnostics, and raises one error naming failed servers. Public `disconnect_all()` always attempts every cleanup step when a loop exists, stops/joins even if async close raises, and changes every state—including `failed`—to `disconnected`; calling it twice is a no-op.

`_run_coroutine(coro, bridge_timeout)` remains a generic bridge that cancels and re-raises on `concurrent.futures.TimeoutError`. `connect_all()` supplies `max(1, len(server_configs)) * connect_timeout + operation_timeout + 2`: every sequential attempt gets its full timeout and failed-startup cleanup gets its own bounded allowance before the outer bridge can cancel. Cleanup is internally bounded by `operation_timeout` and its public-disconnect bridge uses `operation_timeout + 1`. Discovery/tool sync wrappers also use `operation_timeout + 1`, regardless of their legacy optional timeout argument; update/remove that argument consistently at call sites. The recording fake future tests the exact startup, cleanup, and operation deadlines—including a near-timeout connection followed by cleanup—and closes any intercepted coroutine to avoid unawaited-coroutine warnings.

- [ ] **Step 4: Run lifecycle tests**

Run: `python -m pytest tests/test_mcp_client.py -v`

Expected: lifecycle cases PASS.

- [ ] **Step 5: Commit lifecycle work**

```bash
git add shared/clients/mcp_client.py tests/test_mcp_client.py
git commit -m "feat: harden MCP client lifecycle"
```

### Task 2: Paginated discovery cache and operation contracts

**Files:**
- Modify: `shared/clients/mcp_client.py`
- Modify: `tests/test_mcp_client.py`

- [ ] **Step 1: Write failing operation tests**

Use small fake response/tool/session objects and `asyncio.run()` so no pytest async plugin is needed. Cover two discovery pages, cached second lookup, `force=True` refresh, failed refresh preserving but not returning the old cache entry, TTL expiry causing rediscovery, list timeout raising contextual `MCPConnectionError`, call timeout returning `MCPToolResult(success=False)`, and a normal tool-level `isError` result leaving server state connected. A discovered tool is valid only when `name` is a non-empty string, description is absent/string, and input schema is a dictionary; malformed entries must raise and must not be cached. Patch `asyncio.run_coroutine_threadsafe` with a recording fake future to separately prove the outer sync deadline calls `future.result(timeout=operation_timeout + 1)`, cancels on expiry, makes `list_tools_sync` raise the contextual client error, and makes `call_tool_sync` return the failure result contract.

```python
def test_list_tools_follows_pages_and_caches():
    async def exercise():
        session = FakeSession([
            FakeTools([FakeTool("one")], next_cursor="page-2"),
            FakeTools([FakeTool("two")]),
        ])
        client = connected_client(session)
        assert [tool.name for tool in await client.list_tools("hiring")] == ["one", "two"]
        assert [tool.name for tool in await client.list_tools("hiring")] == ["one", "two"]
        assert session.list_calls == [None, "page-2"]

    asyncio.run(exercise())
```

- [ ] **Step 2: Run operation tests and verify failure**

Run: `python -m pytest tests/test_mcp_client.py -v`

Expected: FAIL on pagination, `force`, cache, and timeout assertions.

- [ ] **Step 3: Implement discovery and call behavior**

Reuse `InMemoryCache`; key entries as `mcp:tools:{server_name}` and pass `discovery_ttl` to `set()` only after every page and tool definition validates. Iterate `session.list_tools(cursor=cursor)` until `nextCursor`/`next_cursor` is empty. Reject invalid names/descriptions/schemas with a contextual `MCPConnectionError`. Wrap each SDK operation with `asyncio.wait_for(..., operation_timeout)`. On discovery exception, mark the server failed and raise `MCPConnectionError` without deleting or returning a prior entry. On tool-call exception/timeout, mark failed and return the existing result contract. Do not mark failed when the SDK returned normally with `isError=True`.

Sync discovery raises contextual timeout errors. Sync tool calls catch the outer bridge deadline and return:

```python
MCPToolResult(
    success=False,
    error=f"MCP operation timed out: {server_name}.{tool_name}",
    metadata={"server": server_name, "tool": tool_name},
)
```

- [ ] **Step 4: Run focused client tests**

Run: `python -m pytest tests/test_mcp_client.py -v`

Expected: all focused tests PASS with no pending-task warnings.

- [ ] **Step 5: Commit operation work**

```bash
git add shared/clients/mcp_client.py tests/test_mcp_client.py
git commit -m "feat: cache and paginate MCP discovery"
```

## Chunk 2: Application Lifecycle and Test Isolation

### Task 3: FastAPI/CLI ownership and readiness

**Files:**
- Modify: `apps/chatbot/agent_setup.py`
- Modify: `apps/chatbot/main.py`
- Modify: `chat.py`
- Modify: `tests/test_chatbot_api.py`
- Modify: `tests/test_settings_api.py`
- Create: `tests/test_chatbot_lifecycle.py`
- Create: `tests/test_chat_cli.py`

- [ ] **Step 1: Write failing API lifecycle/readiness tests**

Make the two existing API client fixtures module-scoped and context-managed so each module starts the real three-server stdio client once, not once per test. Add readiness assertions for the connected case and monkeypatch `mcp_client.server_status` to verify the complete passive payload for every configured server:

```python
def test_readiness_reports_server_states(client, monkeypatch):
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "servers": {"hiring": "connected", "attendance": "connected", "employee": "connected"},
    }
    monkeypatch.setitem(mcp_client.server_status, "hiring", "failed")
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "servers": {"hiring": "failed", "attendance": "connected", "employee": "connected"},
    }
```

Add an import-side-effect test in `tests/test_mcp_client.py` which reloads `apps.chatbot.agent_setup` with `connect_all` patched and asserts it was not called. In `tests/test_chatbot_lifecycle.py`, replace `apps.chatbot.main.mcp_client` with a fake recording client before entering `TestClient(app)`: assert connect at entry, disconnect at exit, and a raised connect error propagates out of `TestClient`. These isolated ownership tests do not start stdio processes. In `tests/test_chat_cli.py`, replace `chat.mcp_client` and `chat.run_chat_loop`; make the loop raise and assert `chat.main()` still disconnects.

- [ ] **Step 2: Run API tests and verify failure**

Run: `python -m pytest tests/test_mcp_client.py tests/test_chatbot_lifecycle.py tests/test_chat_cli.py tests/test_chatbot_api.py tests/test_settings_api.py -v`

Expected: readiness route/import ownership assertions FAIL.

- [ ] **Step 3: Move connection ownership to entry points**

Change `setup_mcp_client()` to only construct/configure the client. In `apps/chatbot/main.py`, add an `asynccontextmanager` lifespan that runs blocking connect/disconnect through `asyncio.to_thread`, and pass it to `FastAPI`. Add passive readiness:

```python
@app.get("/health/ready", tags=["Health"])
def readiness(response: Response):
    servers = dict(mcp_client.server_status)
    ready = bool(servers) and all(state == "connected" for state in servers.values())
    response.status_code = 200 if ready else 503
    return {"status": "ready" if ready else "not_ready", "servers": servers}
```

In `chat.py`, import `mcp_client` and wrap the full interactive body:

```python
def main():
    mcp_client.connect_all()
    try:
        run_chat_loop()
    finally:
        mcp_client.disconnect_all()
```

Move the existing prompt/input body unchanged into `run_chat_loop()`. Keep startup failure uncaught so CLI exits nonzero and FastAPI startup fails clearly.

- [ ] **Step 4: Make settings tests restore all state**

Snapshot `dict(os.environ)` and whether `.env` existed. On fixture teardown, restore the full environment; restore prior file content or call `ENV_PATH.unlink(missing_ok=True)` when absent initially. This is test isolation only—do not change Settings API behavior.

- [ ] **Step 5: Run API and settings tests**

Run: `python -m pytest tests/test_mcp_client.py tests/test_chatbot_lifecycle.py tests/test_chat_cli.py tests/test_chatbot_api.py tests/test_settings_api.py -v`

Expected: PASS; `.env` existence/content after the command matches its state before the command.

- [ ] **Step 6: Commit lifecycle ownership**

```bash
git add apps/chatbot/agent_setup.py apps/chatbot/main.py chat.py tests/test_mcp_client.py tests/test_chatbot_lifecycle.py tests/test_chat_cli.py tests/test_chatbot_api.py tests/test_settings_api.py
git commit -m "feat: own MCP lifecycle in API and CLI"
```

### Task 4: Emit each application log once

**Files:**
- Modify: `shared/logger/__init__.py`
- Create: `tests/test_logger.py`

- [ ] **Step 1: Write the failing duplicate-log test**

Create uniquely named parent/child loggers through `setup_logger`, snapshot their handlers/propagation flags, emit one child message, capture stderr, and assert the marker occurs exactly once. Restore those snapshots during teardown so the test cannot disturb application loggers.

- [ ] **Step 2: Run the logging test and verify failure**

Run: `python -m pytest tests/test_logger.py -v`

Expected: FAIL because child records propagate to the configured `fme` parent.

- [ ] **Step 3: Disable propagation for configured loggers**

Set `logger.propagate = False` in `setup_logger`; keep its existing idempotent single-handler logic.

- [ ] **Step 4: Run the logging regression test**

Run: `python -m pytest tests/test_logger.py -v`

Expected: PASS with one marker.

- [ ] **Step 5: Commit logging fix**

```bash
git add shared/logger/__init__.py tests/test_logger.py
git commit -m "fix: emit application logs once"
```

## Chunk 3: Verified Demo and Documentation

### Task 5: Real stdio integration and deterministic three-domain smoke

**Files:**
- Create: `tests/test_mcp_stdio_integration.py`
- Create: `scripts/smoke_mcp_demo.py`

- [ ] **Step 1: Add the real stdio integration test**

Build the same three configs as `setup_mcp_client`, connect once, and in `try/finally` discover exactly five tools per server and call one stable tool per domain with known mock-data arguments. Assert `success`, expected server metadata, and non-empty data; always disconnect.

Use these stable calls:

```python
CASES = {
    "hiring": ("search_candidates", {}),
    "attendance": ("get_monthly_attendance", {"employee_id": "NV001", "month": 8, "year": 2025}),
    "employee": ("get_employee_department", {"identifier": "NV001"}),
}
```

- [ ] **Step 2: Add the deterministic smoke script**

Import `apps.chatbot.agent_setup`, then explicitly set `agent_setup.llm_provider = None` before `build_root_agent(client=client)` so `.env` contents and API keys cannot enable an LLM. Connect the configured client and wrap that client instance's `call_tool_sync`; the wrapper first asserts the returned `MCPToolResult.success` and only then records `(server, tool)`. Submit these exact fixed requests and expectations:

```python
CASES = [
    ("Có bao nhiêu ứng viên đang chờ phỏng vấn?", "hiring", "search_candidates"),
    ("Tháng 8 năm 2025 nhân viên NV001 đi làm bao nhiêu ngày?", "attendance", "get_monthly_attendance"),
    ("Nhân viên NV001 thuộc phòng ban nào?", "employee", "get_employee_department"),
]
EXPECTED_CALLS = {
    ("hiring", "search_candidates"),
    ("attendance", "get_monthly_attendance"),
    ("employee", "get_employee_department"),
}
```

Assert every agent response succeeds, expected `intent`/`tool_used` metadata matches, and the recorded call set equals `EXPECTED_CALLS`. Return exit code 1 with a short failed assertion message; always disconnect.

- [ ] **Step 3: Run both real checks**

Run: `python -m pytest tests/test_mcp_stdio_integration.py -v`

Expected: PASS with three connected servers, 15 discovered tools total, and three successful calls.

Run: `python scripts/smoke_mcp_demo.py`

Expected: exit 0 and one PASS line naming hiring, attendance, and employee.

- [ ] **Step 4: Commit demo checks**

```bash
git add tests/test_mcp_stdio_integration.py scripts/smoke_mcp_demo.py
git commit -m "test: verify three-domain MCP demo"
```

### Task 6: Configuration, dependency reproducibility, and README

**Files:**
- Modify: `.env.example`
- Modify: `apps/chatbot/routers/settings.py`
- Modify: `tests/test_settings_api.py`
- Modify: `requirements.txt`
- Create: `constraints.txt`
- Modify: `README.md`

- [ ] **Step 1: Expose the three verified MCP values**

First extend the existing Settings API save test to assert the generated `.env` contains all three lines. Then add them to `.env.example` and to the `.env` template generated by the settings endpoint:

```dotenv
MCP_CONNECT_TIMEOUT_SECONDS=10
MCP_OPERATION_TIMEOUT_SECONDS=30
MCP_DISCOVERY_TTL_SECONDS=60
```

The client reads the same defaults when variables are absent, so existing deployments remain compatible.

- [ ] **Step 2: Constrain only the audited dependency boundaries**

Change `mcp>=1.0.0` to `mcp>=2,<3`. Create `constraints.txt` containing only:

```text
cryptography==48.0.1
```

- [ ] **Step 3: Update README commands and claims**

Document `pip install -r requirements.txt -c constraints.txt`, `/health/ready`, `python scripts/smoke_mcp_demo.py`, timeout/TTL variables, and shutdown behavior. Replace fixed test counts/output with wording that does not become stale.

- [ ] **Step 4: Run full verification**

Run: `python -m pip install -r requirements.txt -c constraints.txt`

Expected: exit 0 with an MCP 2.x version and `cryptography==48.0.1` resolved together.

Run: `python -m compileall agents apps mcp_servers shared scripts`

Expected: exit 0.

Run: `python -m pytest tests/ -v`

Expected: all tests PASS with no leaked `.env`, pending-task, or unclosed-session warnings.

Run: `python -m pip check`

Expected: `No broken requirements found.`

Run: `python scripts/smoke_mcp_demo.py`

Expected: exit 0 and all three Root Agent → Domain Agent → MCP paths PASS.

- [ ] **Step 5: Inspect final branch and commit**

Run: `git status --short && git diff --check && git log --oneline origin/main..HEAD`

Expected: no whitespace errors; only approved phase-1 files changed.

```bash
git add .env.example apps/chatbot/routers/settings.py tests/test_settings_api.py requirements.txt constraints.txt README.md
git commit -m "docs: document reliable MCP demo setup"
```
