from apps.chatbot.agent_setup import setup_mcp_client


CASES = {
    "hiring": ("search_candidates", {}),
    "attendance": (
        "get_monthly_attendance",
        {"employee_id": "NV001", "month": 8, "year": 2025},
    ),
    "employee": ("get_employee_department", {"identifier": "NV001"}),
}


def test_real_stdio_servers_discover_and_call_tools(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    client = setup_mcp_client()
    try:
        client.connect_all()
        for server, (tool_name, arguments) in CASES.items():
            tools = client.list_tools_sync(server)
            assert len(tools) == 5
            assert tool_name in {tool.name for tool in tools}

            result = client.call_tool_sync(server, tool_name, arguments)
            assert result.success, result.error
            assert result.metadata["server"] == server
            assert result.data
    finally:
        client.disconnect_all()
