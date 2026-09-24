import os
from collections.abc import Mapping
from ipaddress import ip_address
from urllib.parse import urlparse

from .mcp_client import PlatformMCPClient
from .mcp_integration import (
    MCPClientManager,
    MCPConfigurationError,
    MCPServerConfig,
    MemoryTTLCache,
)


def create_platform_mcp_client_from_env(
    environ: Mapping[str, str] | None = None,
) -> PlatformMCPClient:
    """Build the three-server client from the variables in .env.example."""
    values = os.environ if environ is None else environ
    configs = []
    try:
        for prefix in ("HIRING", "ATTENDANCE", "EMPLOYEE"):
            token = values.get(f"{prefix}_MCP_AUTH_TOKEN", "")
            url = values.get(f"{prefix}_MCP_URL", "")
            if token and not _allows_bearer_token(url):
                raise MCPConfigurationError(
                    f"{prefix}_MCP_URL must use HTTPS when an auth token is set"
                )
            configs.append(
                MCPServerConfig(
                    name=values.get(f"{prefix}_MCP_NAME", prefix.lower()),
                    url=url,
                    timeout_seconds=float(
                        values.get(f"{prefix}_MCP_TIMEOUT_SECONDS", "30")
                    ),
                    headers={"Authorization": f"Bearer {token}"} if token else {},
                )
            )
        ttl = float(values.get("MCP_DISCOVERY_TTL_SECONDS", "300"))
    except ValueError as error:
        raise MCPConfigurationError(
            "MCP timeout and discovery TTL values must be numbers"
        ) from error

    return PlatformMCPClient(
        MCPClientManager(configs, MemoryTTLCache(), discovery_ttl_seconds=ttl)
    )


def _allows_bearer_token(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme == "https" or parsed.hostname == "localhost":
        return True
    try:
        return ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        return False
