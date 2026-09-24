import pytest

from agents.hiring.hiring_agent import HiringAgent
from shared.abstractions import AgentRequest
from shared.abstractions import BaseMCPClient, MCPToolResult, ToolDefinition
from shared.clients import (
    MCPClientManager,
    MCPServerConfig,
    MemoryTTLCache,
    PlatformMCPClient,
    create_platform_mcp_client_from_env,
)
from shared.clients.mcp_integration.models import MCPTool, ToolNotFoundError, ToolResult
from shared.clients.mcp_integration import MCPConfigurationError


def test_platform_client_configuration_from_environment():
    client = create_platform_mcp_client_from_env(
        {
            "HIRING_MCP_URL": "https://hiring.test/mcp",
            "HIRING_MCP_AUTH_TOKEN": "secret",
            "ATTENDANCE_MCP_URL": "https://attendance.test/mcp",
            "EMPLOYEE_MCP_URL": "https://employee.test/mcp",
            "MCP_DISCOVERY_TTL_SECONDS": "60",
        }
    )

    configs = client._manager._configs
    assert [config.name for config in configs] == ["hiring", "attendance", "employee"]
    assert configs[0].headers == {"Authorization": "Bearer secret"}
    assert "secret" not in repr(configs[0])


def test_platform_client_rejects_token_over_remote_http():
    with pytest.raises(MCPConfigurationError, match="must use HTTPS"):
        create_platform_mcp_client_from_env(
            {
                "HIRING_MCP_URL": "http://hiring.example.com/mcp",
                "HIRING_MCP_AUTH_TOKEN": "secret",
                "ATTENDANCE_MCP_URL": "https://attendance.test/mcp",
                "EMPLOYEE_MCP_URL": "https://employee.test/mcp",
            }
        )


class FakeServerClient:
    def __init__(self, name, tools):
        self.name = name
        self.tools = tools
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def list_tools(self):
        return self.tools

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return ToolResult(
            (),
            {
                "success": True,
                "data": {
                    "id": arguments["candidate_id"],
                    "name": "Nguyễn Văn An",
                    "position": "Backend Engineer",
                    "job_id": "JOB001",
                    "status": "pending_interview",
                    "experience_years": 3,
                    "skills": ["Python"],
                    "email": "an@example.com",
                    "phone": "0900000000",
                    "applied_date": "2026-08-01",
                },
                "error": None,
                "metadata": {"source": self.name},
            },
            False,
        )


@pytest.mark.asyncio
async def test_platform_client_follows_existing_contract():
    configs = [
        MCPServerConfig("hiring", "https://hiring.test/mcp"),
        MCPServerConfig("attendance", "https://attendance.test/mcp"),
        MCPServerConfig("employee", "https://employee.test/mcp"),
    ]
    clients = {
        "hiring": FakeServerClient(
            "hiring",
            [MCPTool("get_candidate_detail", None, "Get candidate", {"type": "object"}, None)],
        ),
        "attendance": FakeServerClient("attendance", []),
        "employee": FakeServerClient("employee", []),
    }
    manager = MCPClientManager(
        configs,
        MemoryTTLCache(),
        client_constructor=lambda config: clients[config.name],
    )
    client = PlatformMCPClient(manager)

    assert isinstance(client, BaseMCPClient)
    async with client:
        assert await client.list_tools("hiring") == [
            ToolDefinition("get_candidate_detail", "Get candidate", {"type": "object"})
        ]
        result = await client.call_tool(
            "hiring",
            "get_candidate_detail",
            {"candidate_id": "UV001"},
        )

        assert result == MCPToolResult(
            True,
            {
                "id": "UV001",
                "name": "Nguyễn Văn An",
                "position": "Backend Engineer",
                "job_id": "JOB001",
                "status": "pending_interview",
                "experience_years": 3,
                "skills": ["Python"],
                "email": "an@example.com",
                "phone": "0900000000",
                "applied_date": "2026-08-01",
            },
            None,
            {"source": "hiring"},
        )
        with pytest.raises(ToolNotFoundError):
            await client.call_tool(
                "attendance",
                "get_candidate_detail",
                {"candidate_id": "UV001"},
            )

    assert clients["hiring"].calls == [
        ("get_candidate_detail", {"candidate_id": "UV001"})
    ]


@pytest.mark.asyncio
async def test_hiring_agent_awaits_platform_client():
    configs = [
        MCPServerConfig("hiring", "https://hiring.test/mcp"),
        MCPServerConfig("attendance", "https://attendance.test/mcp"),
        MCPServerConfig("employee", "https://employee.test/mcp"),
    ]
    clients = {
        "hiring": FakeServerClient(
            "hiring",
            [MCPTool("get_candidate_detail", None, "Get candidate", {"type": "object"}, None)],
        ),
        "attendance": FakeServerClient("attendance", []),
        "employee": FakeServerClient("employee", []),
    }
    manager = MCPClientManager(
        configs,
        MemoryTTLCache(),
        client_constructor=lambda config: clients[config.name],
    )

    async with PlatformMCPClient(manager) as client:
        response = await HiringAgent(mcp_client=client).handle_async(
            AgentRequest(message="Cho tôi thông tin ứng viên UV001")
        )

    assert response.success is True
    assert response.data["tool_used"] == "get_candidate_detail"
    assert "Nguyễn Văn An" in response.data["response"]
