"""Unit tests for Employee Agent."""

import pytest
from shared.abstractions.agent import AgentRequest
from agents.employee.employee_agent import EmployeeAgent


@pytest.fixture
def agent():
    # Pass openai_client=False to ensure test runs deterministically offline
    return EmployeeAgent(openai_client=False)


def test_agent_empty_message(agent):
    req = AgentRequest(message="")
    res = agent.handle(req)
    assert res.success is False
    assert "trống" in res.error


def test_agent_get_employee_profile(agent):
    req = AgentRequest(message="Tìm thông tin nhân viên có mã NV001")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_employee_profile"
    assert "Nguyễn Văn A" in res.data["response"]
    assert "Phòng Kỹ thuật" in res.data["response"]


def test_agent_get_employee_department(agent):
    req = AgentRequest(message="Nhân viên A thuộc phòng ban nào?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_employee_department"
    assert "Phòng Kỹ thuật" in res.data["response"]


def test_agent_get_department_list(agent):
    req = AgentRequest(message="Công ty có những phòng ban nào?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_department_list"
    assert "Phòng Kỹ thuật" in res.data["response"]
    assert "Phòng Nhân sự" in res.data["response"]


def test_agent_department_member_count(agent):
    req = AgentRequest(message="Phòng ban Kỹ thuật có bao nhiêu nhân viên?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_employee_summary"
    assert "5" in res.data["response"]


def test_agent_general_summary(agent):
    req = AgentRequest(message="Thống kê nhân sự công ty")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_employee_summary"
    assert "Tổng số nhân viên" in res.data["response"]


def test_agent_needs_more_info(agent):
    req = AgentRequest(message="Xem hồ sơ chi tiết nhân viên")
    res = agent.handle(req)
    assert res.success is True
    assert res.data.get("status") == "needs_more_info"
    assert "mã nhân viên" in res.data["response"]


def test_agent_get_employee_department_no_diacritics(agent):
    req = AgentRequest(message="nhan vien A thuoc phong ban nao")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_employee_department"
    assert "Phòng Kỹ thuật" in res.data["response"]


def test_agent_get_department_list_no_diacritics(agent):
    req = AgentRequest(message="danh sach phong ban")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_department_list"
    assert "Phòng Kỹ thuật" in res.data["response"]


def test_agent_department_what(agent):
    req = AgentRequest(message="Nhân viên A phòng ban gì?")
    res = agent.handle(req)
    assert res.success is True
    assert res.data["tool"] == "get_employee_department"
    assert "Phòng Kỹ thuật" in res.data["response"]
