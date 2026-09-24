"""Unit tests for HiringAgent."""

import pytest
from agents.hiring.hiring_agent import HiringAgent
from shared.abstractions.agent import AgentRequest


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return HiringAgent()


def test_agent_empty_message(agent):
    req = AgentRequest(message="   ")
    res = agent.handle(req)
    assert res.success is False
    assert "trống" in res.error


def test_agent_candidate_detail(agent):
    req = AgentRequest(message="Cho tôi thông tin ứng viên có mã UV001")
    res = agent.handle(req)
    assert res.success is True
    assert res.metadata["source"] == "hiring"
    assert res.data["tool_used"] == "get_candidate_detail"
    assert "Nguyễn Văn An" in res.data["response"]
    assert "Kỹ sư Phần mềm Backend" in res.data["response"]


def test_agent_candidate_detail_missing_id(agent):
    req = AgentRequest(message="Cho tôi hồ sơ ứng viên")
    res = agent.handle(req)
    assert res.success is True
    assert res.data.get("status") == "needs_more_info"
    assert "mã ứng viên" in res.data["response"]


def test_agent_waiting_interview(agent):
    req = AgentRequest(message="Có bao nhiêu ứng viên đang chờ phỏng vấn?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool_used"] == "search_candidates"
    assert "Tìm thấy" in res.data["response"]
    assert "Chờ phỏng vấn" in res.data["response"]


def test_agent_job_openings(agent):
    req = AgentRequest(message="Danh sách vị trí đang tuyển là gì?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool_used"] == "list_job_openings"
    assert "vị trí đang tuyển dụng" in res.data["response"]
    assert "Kỹ sư Phần mềm Backend" in res.data["response"]


def test_agent_interview_schedule(agent):
    req = AgentRequest(message="Lịch phỏng vấn tuần này thế nào?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool_used"] == "get_interview_schedule"
    assert "Lịch phỏng vấn" in res.data["response"]


def test_agent_recruitment_summary(agent):
    req = AgentRequest(message="Tổng hợp tình hình tuyển dụng tháng 8")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool_used"] == "get_recruitment_summary"
    assert "Tổng số chỉ tiêu" in res.data["response"]
    assert "Tổng số ứng viên" in res.data["response"]


def test_agent_general_query(agent):
    req = AgentRequest(message="Xin chào, bạn có thể giúp gì?")
    res = agent.handle(req)
    assert res.success is True
    assert "Trợ lý Tuyển dụng" in res.data["response"]


from shared.abstractions.llm import BaseLLM, LLMRequest, LLMResponse


class SpyLLM(BaseLLM):
    """Spy LLM để kiểm chứng Domain Agent thực sự gọi LLM abstraction qua DI."""

    def __init__(self, response_content: str = "Câu trả lời tổng hợp từ SpyLLM."):
        self.response_content = response_content
        self.calls = []
        self.is_mock = False  # Báo hiệu đây là LLM thực tế được inject
        self.config = type("Config", (), {"model": "openai/gpt-oss-120b"})()

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        return LLMResponse(
            content=self.response_content,
            model=request.model,
            metadata={"provider": "spy"},
        )


def test_hiring_agent_uses_injected_llm_for_synthesis():
    """Kiểm tra: Domain Agent nhận LLM qua DI và thực sự gọi llm.generate() để tổng hợp kết quả."""
    spy_llm = SpyLLM(response_content="### Danh sách tổng hợp bởi LLM")
    agent = HiringAgent(llm=spy_llm)

    assert agent.llm is spy_llm
    assert agent.model_name == "openai/gpt-oss-120b"

    req = AgentRequest(message="Danh sách ứng viên đang đợi phỏng vấn")
    res = agent.handle(req)

    assert res.success is True
    assert res.data["tool_used"] == "search_candidates"
    # Chứng minh response được sinh từ LLM chứ không phải template fallback
    assert "### Danh sách tổng hợp bởi LLM" in res.data["response"]
    # Chứng minh llm.generate() đã thực sự được invoke trong execution flow
    assert len(spy_llm.calls) >= 1
    # Ít nhất một cuộc gọi là cho synthesis
    synthesis_call = spy_llm.calls[-1]
    assert any("search_candidates" in m["content"] for m in synthesis_call.messages)


class FailingLLM(BaseLLM):
    """LLM giả lập lỗi API để kiểm tra cơ chế error handling & fallback."""

    def __init__(self):
        self.is_mock = False
        self.config = type("Config", (), {"model": "openai/gpt-oss-120b"})()

    def generate(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("API Timeout / Network error")


def test_hiring_agent_fallback_when_llm_fails():
    """Kiểm tra: Khi LLM lỗi, Agent không crash mà ghi nhận và fallback sang template có dữ liệu."""
    failing_llm = FailingLLM()
    agent = HiringAgent(llm=failing_llm)

    req = AgentRequest(message="Danh sách ứng viên đang đợi phỏng vấn")
    res = agent.handle(req)

    assert res.success is True
    assert res.data["tool_used"] == "search_candidates"
    # Phải có dữ liệu ứng viên từ MCP tool dù LLM lỗi
    assert "UV001" in res.data["response"]
