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


def test_agent_who_was_late_most(agent):
    req = AgentRequest(message="Ai đi trễ nhiều nhất?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_late_arrival_summary"
    assert res.data["parameters"]["employee_id"] == "ALL"
    assert "Nhân viên đi trễ nhiều nhất" in res.data["response"]
    assert "Nguyễn Văn A" in res.data["response"] or "Lê Hoàng C" in res.data["response"]


def test_agent_who_was_late_most_no_diacritics(agent):
    req = AgentRequest(message="ai di tre nhieu nhat")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_late_arrival_summary"
    assert res.data["parameters"]["employee_id"] == "ALL"
    assert "Nhân viên đi trễ nhiều nhất" in res.data["response"]


def test_agent_who_was_absent(agent):
    req = AgentRequest(message="Tháng này ai vắng mặt?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_absence_summary"
    assert res.data["parameters"]["employee_id"] == "ALL"
    assert "Báo cáo nhân viên vắng mặt" in res.data["response"]


def test_agent_dang_mai_k_absence(agent):
    req = AgentRequest(message="Tháng 9 nhân viên Đặng Mai K vắng mặt mấy ngày?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_absence_summary"
    assert res.data["parameters"]["employee_id"] == "NV010"
    assert "Đặng Mai K" in res.data["response"]
    assert "1 ngày" in res.data["response"]


def test_agent_leave_permission_inquiry(agent):
    req = AgentRequest(message="Nhân viên Lê Hoàng C nghỉ có phép hay không phép?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_absence_summary"
    assert res.data["parameters"]["employee_id"] == "NV003"
    assert "Có phép: 1 ngày" in res.data["response"]


def test_agent_company_statistics_month_8(agent):
    req = AgentRequest(message="Tỷ lệ đi làm và đi trễ của toàn công ty trong tháng 8/2026")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_attendance_statistics"
    assert res.data["parameters"]["month"] == 8
    assert "tháng 8/2026" in res.data["response"]


def test_agent_company_overall_report(agent):
    req = AgentRequest(message="Báo cáo tổng hợp tình hình chuyên cần tháng 9")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_attendance_statistics"
    assert res.data["parameters"]["month"] == 9
    assert "Báo cáo chuyên cần tổng hợp" in res.data["response"]

