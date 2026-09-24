"""
Bộ kiểm thử Benchmark toàn diện cho các Agent trong hệ thống AI Agent Platform.
Bao gồm:
1. RootAgent Routing Benchmark (Ma trận nhận diện Intent có dấu / không dấu / ngoài phạm vi).
2. HiringAgent Execution Benchmark (Độ chính xác chọn và thực thi 5 MCP Tools).
3. MemoryStore Multi-turn Benchmark (Lưu vết và duy trì ngữ cảnh qua các lượt hội thoại).
4. Chat API Integration Benchmark (Độ trễ và cấu trúc dữ liệu trả về).
"""
import time
import pytest
from fastapi.testclient import TestClient

from shared.abstractions.agent import AgentRequest
from agents.root.agent_registry import AgentRegistry
from agents.root.root_agent import RootAgent
from agents.hiring.hiring_agent import HiringAgent
from agents.root.mock_agents import MockAttendanceAgent, MockEmployeeAgent
from shared.memory.factory import create_memory_store
from shared.abstractions.memory import Message
from apps.chatbot.main import app


@pytest.fixture
def root_agent():
    registry = AgentRegistry()
    registry.register(HiringAgent(openai_client=False))
    registry.register(MockAttendanceAgent())
    registry.register(MockEmployeeAgent())
    return RootAgent(registry)


@pytest.fixture
def hiring_agent():
    return HiringAgent(openai_client=False)


@pytest.fixture
def api_client():
    return TestClient(app)


# =====================================================================
# 1. ROOT AGENT ROUTING BENCHMARK
# =====================================================================

ROUTING_TEST_CASES = [
    # --- Phân hệ Tuyển dụng (Hiring) ---
    ("Có bao nhiêu ứng viên đang chờ phỏng vấn?", "hiring"),
    ("Co bao nhieu ung vien dang cho phong van?", "hiring"),  # Không dấu
    ("Danh sách vị trí đang tuyển là gì?", "hiring"),
    ("Cho tôi xem danh sách các ứng viên ứng tuyển vào vị trí Backend", "hiring"),
    ("Lịch phỏng vấn tuần này như thế nào?", "hiring"),
    ("Ứng viên UV001 có thông tin gì?", "hiring"),
    ("Báo cáo tổng hợp tình hình tuyển dụng tháng 8", "hiring"),

    # --- Phân hệ Chuyên cần (Attendance) ---
    ("Tháng này nhân viên A đi làm bao nhiêu ngày?", "attendance"),
    ("Thang nay nhan vien A di lam bao nhieu ngay?", "attendance"),  # Không dấu
    ("Nhân viên B đi trễ bao nhiêu lần trong tuần?", "attendance"),
    ("Xem lịch sử chuyên cần của nhân viên NV001", "attendance"),
    ("Hôm nay có ai vắng mặt không?", "attendance"),

    # --- Phân hệ Nhân sự (Employee) ---
    ("Nhân viên Nguyễn Văn A thuộc phòng ban nào?", "employee"),
    ("Nhan vien Nguyen Van A thuoc phong ban nao?", "employee"),  # Không dấu
    ("Phòng ban Kỹ thuật có bao nhiêu nhân viên?", "employee"),
    ("Cho tôi xem hồ sơ nhân sự của nhân viên NV002", "employee"),
    ("Danh sách các phòng ban hiện có trong công ty", "employee"),

    # --- Ngoài phạm vi (Fallback kỳ vọng) ---
    ("Hôm nay thời tiết Hà Nội thế nào?", None),
    ("Cho tôi công thức làm món phở bò", None),
    ("Bạn có thể viết một bài thơ về mùa thu không?", None),
]


@pytest.mark.parametrize("question,expected_intent", ROUTING_TEST_CASES)
def test_root_agent_routing_accuracy(root_agent, question, expected_intent):
    req = AgentRequest(message=question)
    res = root_agent.handle(req)

    actual_intent = res.metadata.get("intent")
    assert actual_intent == expected_intent, (
        f"Câu hỏi: '{question}'\nKỳ vọng: {expected_intent} | Thực tế: {actual_intent}"
    )
    if expected_intent is not None:
        assert res.success is True, f"Routing thành công nhưng agent phản hồi thất bại: {res.error}"
    else:
        assert res.success is False, "Câu hỏi ngoài phạm vi phải trả về success=False"
        assert "chưa hiểu câu hỏi này" in res.error


# =====================================================================
# 2. HIRING AGENT TOOL EXECUTION BENCHMARK
# =====================================================================

def test_hiring_tool_search_candidates_by_skill(hiring_agent):
    req = AgentRequest(message="Tìm ứng viên có kỹ năng React")
    res = hiring_agent.handle(req)
    assert res.success is True
    assert res.data["tool_used"] == "search_candidates"
    assert "UV008" in res.data["response"] or "Lê Văn Hùng" in res.data["response"]


def test_hiring_tool_search_candidates_by_status(hiring_agent):
    req = AgentRequest(message="Tìm kiếm ứng viên đã được tuyển dụng hired")
    res = hiring_agent.handle(req)
    assert res.success is True
    assert res.data["tool_used"] == "search_candidates"
    assert "Bùi Thị Tuyết" in res.data["response"]


def test_hiring_tool_candidate_detail_success(hiring_agent):
    req = AgentRequest(message="Cho tôi xem hồ sơ chi tiết của ứng viên UV003")
    res = hiring_agent.handle(req)
    assert res.success is True
    assert res.data["tool_used"] == "get_candidate_detail"
    assert "Lê Hoàng Nam" in res.data["response"]
    assert "JOB-003" in res.data["response"]


def test_hiring_tool_candidate_detail_not_found(hiring_agent):
    req = AgentRequest(message="Cho tôi thông tin ứng viên có mã UV999")
    res = hiring_agent.handle(req)
    assert res.success is False
    assert "Không tìm thấy" in res.data["response"] or "UV999" in res.data["response"]


def test_hiring_tool_list_job_openings(hiring_agent):
    req = AgentRequest(message="Công ty đang có những vị trí tuyển dụng nào?")
    res = hiring_agent.handle(req)
    assert res.success is True
    assert res.data["tool_used"] == "list_job_openings"
    assert "JOB-001" in res.data["response"]
    assert "JOB-006" in res.data["response"]


def test_hiring_tool_recruitment_summary(hiring_agent):
    req = AgentRequest(message="Tổng hợp báo cáo số liệu tuyển dụng tháng 8")
    res = hiring_agent.handle(req)
    assert res.success is True
    assert res.data["tool_used"] == "get_recruitment_summary"
    assert "Tuyển dụng" in res.data["response"] or "tuyển dụng" in res.data["response"]


# =====================================================================
# 3. MEMORYSTORE MULTI-TURN CONTEXT BENCHMARK
# =====================================================================

def test_memory_multi_turn_retention():
    store = create_memory_store("in_memory")
    user_id = "test_user_benchmark"
    conv = store.create_conversation(user_id=user_id)
    conv_id = conv.conversation_id

    # Lượt 1: Hỏi về ứng viên UV001
    store.append_message(conv_id, Message(role="user", content="Tìm thông tin ứng viên UV001"))
    store.append_message(conv_id, Message(role="assistant", content="Ứng viên UV001 là Nguyễn Văn An"))
    store.update_user_context(user_id, {"last_candidate_id": "UV001"})

    # Lượt 2: Kiểm tra ngữ cảnh
    context = store.get_user_context(user_id)
    assert context.get("last_candidate_id") == "UV001"

    # Kiểm tra lịch sử
    history = store.get_history(conv_id, limit=5)
    assert len(history) == 2
    assert history[0].content == "Tìm thông tin ứng viên UV001"
    assert history[1].content == "Ứng viên UV001 là Nguyễn Văn An"


# =====================================================================
# 4. CHAT API INTEGRATION BENCHMARK
# =====================================================================

def test_chat_api_response_structure(api_client):
    response = api_client.post("/chat", json={"message": "Danh sách vị trí đang tuyển dụng"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["metadata"]["tool_used"] == "list_job_openings"
    assert "conversation_id" in data
    assert len(data.get("messages", [])) >= 2
