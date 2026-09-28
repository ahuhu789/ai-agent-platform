import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.chatbot import agent_setup
from shared.abstractions.agent import AgentRequest


CASES = [
    ("Có bao nhiêu ứng viên đang chờ phỏng vấn?", "hiring", "search_candidates"),
    (
        "Tháng 8 năm 2025 nhân viên NV001 đi làm bao nhiêu ngày?",
        "attendance",
        "get_monthly_attendance",
    ),
    ("Nhân viên NV001 thuộc phòng ban nào?", "employee", "get_employee_department"),
]
EXPECTED_CALLS = {
    ("hiring", "search_candidates"),
    ("attendance", "get_monthly_attendance"),
    ("employee", "get_employee_department"),
}


def main() -> int:
    agent_setup.llm_provider = None
    client = agent_setup.setup_mcp_client()
    calls = set()
    call_tool_sync = client.call_tool_sync

    def record_call(server, tool, arguments):
        result = call_tool_sync(server, tool, arguments)
        assert result.success, result.error
        calls.add((server, tool))
        return result

    client.call_tool_sync = record_call
    try:
        client.connect_all()
        agent = agent_setup.build_root_agent(client=client)
        for message, intent, tool in CASES:
            response = agent.handle(AgentRequest(message=message))
            assert response.success, response.error
            assert response.metadata.get("intent") == intent, response.metadata
            assert response.metadata.get("tool_used") == tool, response.metadata
        assert calls == EXPECTED_CALLS, calls
    except AssertionError as exc:
        print(f"FAIL: {exc}")
        return 1
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1
    finally:
        client.disconnect_all()

    print("PASS: hiring, attendance, employee")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
