"""
agents/root/test_root_agent.py

Test routing của Root Agent với nhiều dạng câu hỏi khác nhau,
bao gồm cả trường hợp khó (câu ghép, mơ hồ, không dấu).

Chạy: python -m agents.root.test_root_agent
"""

from shared.abstractions.agent import AgentRequest
from agents.root.agent_registry import AgentRegistry
from agents.root.root_agent import RootAgent
from agents.root.mock_agents import MockHiringAgent, MockAttendanceAgent, MockEmployeeAgent


def build_root_agent() -> RootAgent:
    registry = AgentRegistry()
    registry.register(MockHiringAgent())
    registry.register(MockAttendanceAgent())
    registry.register(MockEmployeeAgent())
    return RootAgent(registry)


# Mỗi test case: (câu hỏi, intent kỳ vọng - None nghĩa là kỳ vọng fallback)
TEST_CASES = [
    # --- Câu hỏi rõ ràng, đúng 1 phân hệ (case cơ bản) ---
    ("Có bao nhiêu ứng viên đang chờ phỏng vấn?", "hiring"),
    ("Danh sách vị trí đang tuyển là gì?", "hiring"),
    ("Tháng này nhân viên A đi làm bao nhiêu ngày?", "attendance"),
    ("Nhân viên A đi trễ bao nhiêu lần?", "attendance"),
    ("Nhân viên A thuộc phòng ban nào?", "employee"),
    ("Phòng ban Kỹ thuật có bao nhiêu nhân viên?", "employee"),

    # --- Câu ngoài phạm vi, kỳ vọng fallback ---
    ("Hôm nay thời tiết thế nào?", None),
    ("Cho tôi công thức nấu phở", None),

    # --- Trường hợp không dấu: giờ đã xử lý được ---
    ("Co bao nhieu ung vien dang cho phong van?", "hiring"),
    ("Nhan vien A thuoc phong ban nao?", "employee"),
    ("Thang nay nhan vien A di lam bao nhieu ngay?", "attendance"),

    # --- Trường hợp khó: câu ghép nhiều ý (2 phân hệ trong 1 câu) ---
    ("Nhân viên A đi làm mấy ngày và thuộc phòng ban nào?", "attendance"),  # match từ khóa đầu tiên tìm thấy, cần bàn lại cách xử lý

    # --- Trường hợp mơ hồ giữa 2 phân hệ ---
    ("Cho tôi thông tin nhân viên đang ứng tuyển", "hiring"),  # "nhân viên" match employee, "ứng tuyển" gần hiring -> dễ nhầm
    ("Nhân viên A nghỉ phép mấy ngày?", "attendance"),
    ("Nhân viên A đi muộn mấy lần?", "attendance"),
    ("Ai đi trễ nhiều nhất?", "attendance"),
    ("ai di tre nhieu nhat", "attendance"),
    ("Tháng này ai vắng mặt?", "attendance"),
    ("Nhan vien A phong ban gi?", "employee"),

    # --- Trường hợp biên: message rỗng ---
    ("", None),
]


def test_empty_and_none_message():
    """Kiểm tra riêng: message rỗng/None không được làm crash Root Agent."""
    root_agent = build_root_agent()

    res_empty = root_agent.handle(AgentRequest(message=""))
    assert res_empty.success is False, "Message rỗng phải rơi vào fallback, không crash"

    res_none = root_agent.handle(AgentRequest(message=None))
    assert res_none.success is False, "Message None phải rơi vào fallback, không crash"

    print("[OK] message rỗng/None không làm crash Root Agent")


def test_duplicate_registration_warns():
    """Kiểm tra: đăng ký trùng tên Agent phải in cảnh báo, không được crash."""
    registry = AgentRegistry()
    registry.register(MockHiringAgent())
    registry.register(MockHiringAgent())  # đăng ký trùng "hiring" lần 2 - phải in cảnh báo, không lỗi
    assert registry.get("hiring") is not None
    print("[OK] Đăng ký trùng tên Agent không làm crash (chỉ cảnh báo)")


import pytest


@pytest.mark.parametrize("question,expected_intent", TEST_CASES)
def test_root_agent_routing(question, expected_intent):
    root_agent = build_root_agent()
    response = root_agent.handle(AgentRequest(message=question))
    actual_intent = response.metadata.get("intent")
    assert actual_intent == expected_intent


def test_root_agent_never_routes_to_system_or_root_agent():
    """Đảm bảo nếu context có last_agent là 'root_agent' hoặc 'chat_service', RootAgent không bao giờ route tới nó."""
    root_agent = build_root_agent()
    # Giả sử lượt trước lỗi và last_agent bị lưu là root_agent hoặc chat_service
    for invalid_agent in ["root_agent", "root", "chat_service", "system"]:
        req = AgentRequest(
            message="chi tiết",
            context={"last_agent": invalid_agent}
        )
        res = root_agent.handle(req)
        # Phải rơi vào fallback 'chưa hiểu câu hỏi', không được báo 'Phân hệ {invalid_agent} hiện chưa sẵn sàng'
        assert res.success is False
        assert f"Phân hệ '{invalid_agent}' hiện chưa sẵn sàng." not in (res.error or "")
        assert res.metadata.get("intent") is None


def test_memory_store_never_tracks_system_agents():
    """Đảm bảo memory_store.track_interaction không lưu root_agent/chat_service làm last_agent."""
    from apps.chatbot.memory_store import memory_store
    conv_id = "test_system_agent_tracking"
    user_id = "user_system_test"

    # Giả lập response từ root_agent khi không hiểu câu hỏi
    memory_store.track_interaction(
        conversation_id=conv_id,
        user_id=user_id,
        user_message="câu hỏi linh tinh",
        metadata={"source": "root_agent", "intent": None}
    )

    ctx = memory_store.build_chat_context(conv_id, user_id=user_id)
    assert ctx.get("last_agent") != "root_agent"
    assert ctx.get("last_agent") is None


if __name__ == "__main__":
    run_tests()
    print()
    test_empty_and_none_message()
    test_duplicate_registration_warns()
    test_root_agent_never_routes_to_system_or_root_agent()
    test_memory_store_never_tracks_system_agents()