import unicodedata

from shared.abstractions.agent import AgentRequest, AgentResponse
from agents.root.agent_registry import AgentRegistry


def strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp được cả câu có dấu và không dấu.
    Ví dụ: "Có bao nhiêu ứng viên" -> "co bao nhieu ung vien"
    """
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", text)


# Từ khóa được xếp theo mức độ ưu tiên: match ở nhóm trên trước, nhóm dưới sau.
# Lý do: một số từ (vd "nhân viên") xuất hiện chung ở nhiều phân hệ, nên những
# từ khóa "đặc trưng" hơn (chỉ riêng 1 phân hệ) cần được ưu tiên kiểm tra trước.
INTENT_KEYWORDS = {
    "hiring": ["ứng viên", "phỏng vấn", "tuyển dụng", "vị trí tuyển", "đang tuyển", "ứng tuyển"],
    "attendance": ["đi làm", "đi trễ", "vắng mặt", "chuyên cần", "chấm công"],
    "employee": ["nhân viên", "phòng ban", "hồ sơ", "nhân sự"],
}

# Bản không dấu của từ khóa, tính sẵn 1 lần khi load module (đỡ tính lại mỗi lần gọi)
INTENT_KEYWORDS_NO_DIACRITICS = {
    intent: [strip_diacritics(kw) for kw in keywords]
    for intent, keywords in INTENT_KEYWORDS.items()
}

# Thứ tự ưu tiên kiểm tra khi câu hỏi match nhiều phân hệ cùng lúc.
# hiring và attendance có từ khóa đặc trưng hơn nên xét trước employee.
INTENT_PRIORITY = ["hiring", "attendance", "employee"]


def classify_intent(message: str):
    """Xác định câu hỏi thuộc phân hệ nào dựa theo từ khóa.

    Trả về tên phân hệ ("hiring"/"attendance"/"employee") nếu khớp,
    hoặc None nếu không khớp phân hệ nào (Root Agent sẽ dùng để fallback).
    """
    if not message:
        # Phòng trường hợp Chat Service gửi message rỗng/None do lỗi phía họ -
        # không nên để crash, cứ coi như không xác định được phân hệ.
        return None

    message_lower = message.lower()
    message_no_diacritics = strip_diacritics(message_lower)

    for intent in INTENT_PRIORITY:
        # So khớp cả bản có dấu (nhanh, chính xác) lẫn bản không dấu (bắt thêm case gõ tắt)
        if any(kw in message_lower for kw in INTENT_KEYWORDS[intent]):
            return intent
        if any(kw in message_no_diacritics for kw in INTENT_KEYWORDS_NO_DIACRITICS[intent]):
            return intent
    return None


class RootAgent:
    """Đầu mối điều phối: nhận câu hỏi, xác định phân hệ, gọi đúng Agent.

    Root Agent KHÔNG tự xử lý nghiệp vụ, KHÔNG gọi MCP trực tiếp - chỉ định
    tuyến (route) và trả nguyên kết quả từ Agent phân hệ về.
    """

    def __init__(self, registry: AgentRegistry):
        # Nhận registry từ bên ngoài truyền vào (dependency injection) thay vì
        # tự tạo bên trong - giúp dễ test (có thể truyền registry giả khi test)
        # và dễ thay đổi danh sách Agent mà không phải sửa RootAgent.
        self.registry = registry

    def handle(self, request: AgentRequest) -> AgentResponse:
        intent = classify_intent(request.message)

        if intent is None:
            return AgentResponse(
                success=False,
                error="Xin lỗi, tôi chưa hiểu câu hỏi này thuộc phân hệ nào "
                      "(Tuyển dụng / Nhân sự / Chuyên cần). Bạn có thể nói rõ hơn không?",
                metadata={"source": "root_agent", "intent": None},
            )

        target_agent = self.registry.get(intent)

        if target_agent is None:
            # Trường hợp classify_intent nhận diện đúng phân hệ, nhưng chưa có
            # Agent nào được đăng ký cho phân hệ đó (vd đồng đội chưa xong Agent thật
            # và cũng chưa đăng ký Mock Agent thay thế).
            return AgentResponse(
                success=False,
                error=f"Phân hệ '{intent}' hiện chưa sẵn sàng.",
                metadata={"source": "root_agent", "intent": intent},
            )

        response = target_agent.handle(request)
        response.metadata["routed_by"] = "root_agent"
        response.metadata["intent"] = intent
        return response


if __name__ == "__main__":
    from agents.root.mock_agents import MockHiringAgent, MockAttendanceAgent, MockEmployeeAgent

    registry = AgentRegistry()
    registry.register(MockHiringAgent())
    registry.register(MockAttendanceAgent())
    registry.register(MockEmployeeAgent())

    root_agent = RootAgent(registry)

    test_questions = [
        "Có bao nhiêu ứng viên đang chờ phỏng vấn?",
        "Tháng này nhân viên A đi làm bao nhiêu ngày?",
        "Nhân viên A thuộc phòng ban nào?",
        "Hôm nay thời tiết thế nào?",
    ]

    for q in test_questions:
        req = AgentRequest(message=q)
        res = root_agent.handle(req)
        print(f"\nCâu hỏi: {q}")
        print(f"Kết quả: {res}")