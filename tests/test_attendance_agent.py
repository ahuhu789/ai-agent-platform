"""Unit tests for Attendance Agent."""

import pytest
from shared.abstractions.agent import AgentRequest
from agents.attendance.attendance_agent import AttendanceAgent


@pytest.fixture
def agent():
    return AttendanceAgent(openai_client=False)


def test_agent_empty_message(agent):
    req = AgentRequest(message="")
    res = agent.handle(req)
    assert res.success is False
    assert "trống" in res.error


def test_agent_days_worked_this_month(agent):
    req = AgentRequest(message="Tháng này nhân viên A đi làm bao nhiêu ngày?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_monthly_attendance"
    assert "18" in res.data["response"]
    assert "Nguyễn Văn A" in res.data["response"]


def test_agent_late_arrivals(agent):
    req = AgentRequest(message="Nhân viên A đi trễ bao nhiêu lần?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_late_arrival_summary"
    assert "2 lần" in res.data["response"]


def test_agent_attendance_history(agent):
    req = AgentRequest(message="Cho tôi lịch sử chuyên cần từ ngày 2026-09-01 đến ngày 2026-09-24")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_attendance_history"
    assert "Lịch sử chuyên cần" in res.data["response"]


def test_agent_absence_summary(agent):
    req = AgentRequest(message="Nhân viên NV001 có vắng mặt ngày nào không?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_absence_summary"
    assert "1 ngày" in res.data["response"]


def test_agent_general_attendance_statistics(agent):
    req = AgentRequest(message="Thống kê chuyên cần toàn công ty")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_attendance_statistics"
    assert "Báo cáo chuyên cần tổng hợp" in res.data["response"]
