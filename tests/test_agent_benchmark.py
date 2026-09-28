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
from agents.attendance.attendance_agent import AttendanceAgent
from agents.employee.employee_agent import EmployeeAgent
from shared.memory.factory import create_memory_store
from shared.abstractions.memory import Message
from apps.chatbot import agent_setup
from apps.chatbot.main import app
from apps.chatbot.services.chat_service import chat_service


@pytest.fixture
def root_agent():
    registry = AgentRegistry()
    registry.register(HiringAgent(openai_client=False))
    registry.register(AttendanceAgent(openai_client=False))
    registry.register(EmployeeAgent(openai_client=False))
    return RootAgent(registry)


@pytest.fixture
def hiring_agent():
    return HiringAgent(openai_client=False)


@pytest.fixture
def attendance_agent():
    return AttendanceAgent(openai_client=False)


@pytest.fixture
def employee_agent():
    return EmployeeAgent(openai_client=False)



@pytest.fixture(scope="module")
def api_client():
    original_llm = agent_setup.llm_provider
    original_root_agent = chat_service.root_agent
    try:
        agent_setup.llm_provider = None
        with TestClient(app) as client:
            chat_service.root_agent = agent_setup.build_root_agent(
                client=agent_setup.mcp_client
            )
            yield client
    finally:
        agent_setup.llm_provider = original_llm
        chat_service.root_agent = original_root_agent


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
# 3. ATTENDANCE & EMPLOYEE AGENT BENCHMARK
# =====================================================================

def test_attendance_benchmark_days_worked(attendance_agent):
    req = AgentRequest(message="Tháng này nhân viên A đi làm bao nhiêu ngày?")
    res = attendance_agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_monthly_attendance"
    assert "18" in res.data["response"]
    assert "Nguyễn Văn A" in res.data["response"]


def test_attendance_benchmark_late_summary(attendance_agent):
    req = AgentRequest(message="Nhân viên A đi trễ bao nhiêu lần?")
    res = attendance_agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_late_arrival_summary"
    assert "2 lần" in res.data["response"]


def test_employee_benchmark_department_lookup(employee_agent):
    req = AgentRequest(message="Nhân viên Nguyễn Văn A thuộc phòng ban nào?")
    res = employee_agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_employee_department"
    assert "Phòng Kỹ thuật" in res.data["response"]


def test_employee_benchmark_department_summary(employee_agent):
    req = AgentRequest(message="Phòng ban Kỹ thuật có bao nhiêu nhân viên?")
    res = employee_agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_employee_summary"
    assert "5" in res.data["response"]


def test_employee_benchmark_profile_lookup(employee_agent):
    req = AgentRequest(message="Tìm thông tin nhân viên có mã NV001")
    res = employee_agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_employee_profile"
    assert "Nguyễn Văn A" in res.data["response"]


# =====================================================================
# 4. MEMORYSTORE MULTI-TURN CONTEXT BENCHMARK
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
# 5. CHAT API INTEGRATION BENCHMARK
# =====================================================================

def test_chat_api_response_structure(api_client):
    response = api_client.post("/chat", json={"message": "Danh sách vị trí đang tuyển dụng"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["metadata"]["tool_used"] == "list_job_openings"
    assert "conversation_id" in data
    assert len(data.get("messages", [])) >= 2


def test_chat_multi_turn_cross_domain_benchmark(api_client):
    """Benchmark kiểm thử hội thoại đa lượt và lưu trữ ngữ cảnh liên phân hệ Tuyển dụng, Nhân sự, Chuyên cần."""
    # Turn 1: Hỏi thông tin ứng viên UV001 (Tuyển dụng)
    res1 = api_client.post("/chat", json={"message": "Ứng viên UV001 có thông tin gì?"})
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["success"] is True
    assert d1["metadata"]["intent"] == "hiring"
    assert "UV001" in d1["reply"]
    conv_id = d1["conversation_id"]

    # Turn 2: Hỏi tiếp về ứng viên này không cần nhắc mã UV001 (Đại từ "bạn này")
    res2 = api_client.post("/chat", json={"conversation_id": conv_id, "message": "Xem hồ sơ bạn này"})
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["success"] is True
    assert d2["metadata"]["intent"] == "hiring"
    assert "UV001" in d2["reply"]

    # Turn 3: Chuyển sang hỏi về nhân viên NV002 (Nhân sự)
    res3 = api_client.post("/chat", json={"conversation_id": conv_id, "message": "Cho tôi xem hồ sơ nhân sự của nhân viên NV002"})
    assert res3.status_code == 200
    d3 = res3.json()
    assert d3["success"] is True
    assert d3["metadata"]["intent"] == "employee"
    assert "Trần Thị B" in d3["reply"]

    # Turn 4: Hỏi tiếp về chuyên cần trong tháng 8 của người này mà không nhắc lại mã hay tên (Chuyên cần)
    res4 = api_client.post("/chat", json={"conversation_id": conv_id, "message": "Tháng 8 người này đi làm bao nhiêu ngày?"})
    assert res4.status_code == 200
    d4 = res4.json()
    assert d4["success"] is True
    assert d4["metadata"]["intent"] == "attendance"
    assert ("Trần Thị B" in d4["reply"] or "NV002" in d4["reply"])

