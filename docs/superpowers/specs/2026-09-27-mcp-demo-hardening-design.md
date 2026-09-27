# MCP Demo Hardening Design

## Goal

Make the existing three-server stdio MCP flow deterministic and observable for local demos without replacing the platform's current `BaseMCPClient` contract or adding a second transport.

## Scope

This phase covers MCP lifecycle, readiness, operation timeouts, tool-discovery caching, configuration, focused tests, deterministic demo setup, logging cleanup, and documentation. It does not add authentication, Docker/CI, Redis-backed MCP caching, Streamable HTTP, retries, or production observability.

## Architecture

`MultiServerMCPClient` remains the single concrete client. Construction becomes side-effect free: the background event loop and MCP subprocesses start only when `connect_all()` runs. FastAPI owns the client through its lifespan, while the CLI owns it through `try/finally`; both always close sessions, stop the loop, and join the thread.

The client tracks `disconnected`, `connecting`, `connected`, or `failed` for every configured server. Startup attempts every connection with a per-server timeout. If any connection fails, `connect_all()` closes every partial session, stops and joins the loop thread it started, preserves the failed/disconnected statuses, then raises one stable startup error. FastAPI startup and the CLI both fail rather than serve a degraded agent. After successful startup, `/health` remains liveness-only; `/health/ready` returns HTTP 200 when every server is connected or HTTP 503 with every server state if a later connection is lost. The CLI exits nonzero on startup failure.

Each async MCP operation is wrapped in its own operation timeout. A synchronous timeout cancels the submitted coroutine. Discovery timeout/failure raises an error with server and operation context; tool-call timeout/failure keeps the existing `MCPToolResult(success=False, error=...)` contract. Async discovery follows all cursor pages, validates converted tool definitions, and stores only successful per-server discovery results in the existing `InMemoryCache`. Normal discovery reads the TTL cache; `force=True` bypasses it. A failed refresh never returns stale data or replaces a successful cached value. Tool-call results are never cached.

## Configuration

The local demo stays on stdio. `agent_setup` continues to define the three Python module commands, while these environment values become active:

- `MCP_CONNECT_TIMEOUT_SECONDS` (default `10`)
- `MCP_OPERATION_TIMEOUT_SECONDS` (default `30`)
- `MCP_DISCOVERY_TTL_SECONDS` (default `60`)

Invalid, non-positive, or non-finite values fail during setup with safe messages. `requirements.txt` constrains the SDK to `mcp>=2,<3`; `constraints.txt` pins `cryptography==48.0.1`, the wheel-backed version verified during the clean audit. Local installation and dependency checks use `pip install -r requirements.txt -c constraints.txt`.

## Demo Reliability

Settings tests restore both the `.env` file and process environment; when no `.env` existed before a test, teardown removes the generated file. The shared logger emits each record once. A deterministic smoke script runs one fixed request for each supported domain with LLM disabled, records the selected Domain Agent and MCP server/tool call, asserts all three expected paths and successful results, and exits nonzero on any missing path or failure. README test counts are not hard-coded.

## Error Handling

Connection and operation failures retain the server and operation context. Failed startup leaves no live sessions or loop thread. A failed discovery refresh preserves the previous cache entry for a later normal lookup but does not return it from the failed request. Shutdown attempts every cleanup step and remains safe when called more than once.

## Testing

Focused tests cover side-effect-free construction, three-server startup, partial startup failure, idempotent shutdown, timeout cancellation, paginated discovery, TTL hits, forced refresh, and readiness output. One real stdio integration test discovers and calls a tool on each of the three servers. The full existing suite and the deterministic demo must pass.

## Success Criteria

- Importing API modules starts no MCP subprocess.
- API/CLI startup connects all three servers or reports not-ready clearly.
- API/CLI shutdown leaves no owned MCP sessions or background loop.
- Discovery cache and force refresh are observable in tests.
- Tests do not create a persistent `.env` when none existed.
- Full regression suite, compile check, dependency check, and three-domain demo pass.
