"""Interactive demo script for Hiring Agent and MCP Tools."""

import sys
import io

# Ensure UTF-8 output on Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from agents.hiring.hiring_agent import HiringAgent
from shared.abstractions.agent import AgentRequest


def run_demo():
    agent = HiringAgent()

    test_queries = [
        "1. Có bao nhiêu ứng viên đang chờ phỏng vấn?",
        "2. Danh sách vị trí đang tuyển là gì?",
        "3. Cho tôi thông tin ứng viên có mã UV001",
        "4. Lịch phỏng vấn tuần này như thế nào?",
        "5. Tổng hợp tình hình tuyển dụng tháng 8",
        "6. Cho tôi hồ sơ ứng viên",  # Missing ID test
        "7. Xin chào, bạn có thể giúp gì?",  # General help
    ]

    print("=" * 70)
    print("DEMO PHÂN HỆ TUYỂN DỤNG (HIRING AGENT & MCP TOOLS) - NGUYỄN HUY THANH")
    print("=" * 70)

    for query in test_queries:
        print(f"\n USER: {query}")
        req = AgentRequest(message=query, conversation_id="demo_conv_1", user_id="demo_user_1")
        res = agent.handle(req)

        print(f" HIRING AGENT (Tool: {res.metadata.get('tool_used', 'None')}):")
        print(res.data.get("response", ""))
        print("-" * 70)


if __name__ == "__main__":
    run_demo()
