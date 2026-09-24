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


def run_tests():
    root_agent = build_root_agent()
    passed, failed = 0, 0

    for question, expected_intent in TEST_CASES:
        response = root_agent.handle(AgentRequest(message=question))
        actual_intent = response.metadata.get("intent")

        status = "OK" if actual_intent == expected_intent else "SAI"
        if status == "OK":
            passed += 1
        else:
            failed += 1

        print(f"[{status}] '{question}'")
        print(f"       kỳ vọng: {expected_intent} | thực tế: {actual_intent}")

    print(f"\n--- Kết quả: {passed} đúng / {failed} sai / {len(TEST_CASES)} tổng ---")


if __name__ == "__main__":
    run_tests()
    print()
    test_empty_and_none_message()
    test_duplicate_registration_warns()