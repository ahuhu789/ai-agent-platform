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
