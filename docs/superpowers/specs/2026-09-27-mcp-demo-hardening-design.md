# MCP Demo Hardening Design

## Goal

Make the existing three-server stdio MCP flow deterministic and observable for local demos without replacing the platform's current `BaseMCPClient` contract or adding a second transport.

## Scope

This phase covers MCP lifecycle, readiness, operation timeouts, tool-discovery caching, configuration, focused tests, deterministic demo setup, logging cleanup, and documentation. It does not add authentication, Docker/CI, Redis-backed MCP caching, Streamable HTTP, retries, or production observability.

## Architecture

`MultiServerMCPClient` remains the single concrete client. Construction becomes side-effect free: the background event loop and MCP subprocesses start only when `connect_all()` runs. FastAPI owns the client through its lifespan, while the CLI owns it through `try/finally`; both always close sessions, stop the loop, and join the thread.

The client tracks a status for every configured server. Startup attempts every connection, then raises one stable startup error when any server is unavailable. `/health` remains a liveness endpoint; `/health/ready` reports readiness and per-server connection state without starting new work.

Each MCP operation uses an explicit timeout. A synchronous timeout cancels the submitted coroutine. Async discovery follows all cursor pages, validates converted tool definitions, and stores only successful per-server discovery results in the existing `InMemoryCache`. Normal discovery reads the TTL cache; `force=True` bypasses it. Tool-call results are never cached.

## Configuration

The local demo stays on stdio. `agent_setup` continues to define the three Python module commands, while these environment values become active:

- `MCP_CONNECT_TIMEOUT_SECONDS`
- `MCP_OPERATION_TIMEOUT_SECONDS`
- `MCP_DISCOVERY_TTL_SECONDS`

Invalid, non-positive, or non-finite values fail during setup with safe messages. `requirements.txt` constrains the SDK to `mcp>=2,<3`; a small constraints file pins the transitive cryptography version that failed during the clean audit install.

## Demo Reliability

Settings tests restore both the `.env` file and process environment; when no `.env` existed before a test, teardown removes the generated file. The shared logger emits each record once. A new deterministic smoke script exercises Root Agent → all three Domain Agents → MCP servers with LLM disabled, then exits cleanly. README test counts are not hard-coded.

## Error Handling

Connection and operation failures retain the server and operation context. Failed startup leaves no live sessions. Partial refresh failure keeps the previous cached discovery value. Shutdown attempts every cleanup step and remains safe when called more than once.

## Testing

Focused tests cover side-effect-free construction, three-server startup, partial startup failure, idempotent shutdown, timeout cancellation, paginated discovery, TTL hits, forced refresh, and readiness output. One real stdio integration test discovers and calls a tool on each of the three servers. The full existing suite and the deterministic demo must pass.

## Success Criteria

- Importing API modules starts no MCP subprocess.
- API/CLI startup connects all three servers or reports not-ready clearly.
- API/CLI shutdown leaves no owned MCP sessions or background loop.
- Discovery cache and force refresh are observable in tests.
- Tests do not create a persistent `.env` when none existed.
- Full regression suite, compile check, dependency check, and three-domain demo pass.
