"""Unit tests for Employee MCP Server tools and validation."""

import pytest
from mcp_servers.employee.function_support import MockEmployeeSupport
from mcp_servers.employee.tools import EmployeeTools
from mcp_servers.employee.validators import (
    validate_department_id,
    validate_employee_id,
    validate_employee_status,
)


@pytest.fixture
def tools():
    return EmployeeTools(MockEmployeeSupport())


def test_employee_validators():
    # Employee ID validation
    assert validate_employee_id("NV001")[0] is True
    assert validate_employee_id("")[0] is False
    assert validate_employee_id(None)[0] is False

    # Department ID validation
    assert validate_department_id("DEP-TECH")[0] is True
    assert validate_department_id("")[0] is False

    # Status validation
    assert validate_employee_status("active")[0] is True
    assert validate_employee_status("on_leave")[0] is True
    assert validate_employee_status("resigned")[0] is True
    assert validate_employee_status("invalid_status")[0] is False


def test_search_employees(tools):
    # Search all
    res = tools.search_employees()
    assert res["success"] is True
    assert res["metadata"]["source"] == "employee"
    assert len(res["data"]["employees"]) > 0

    # Search by keyword
    res = tools.search_employees(keyword="Kỹ thuật")
    assert res["success"] is True
    assert len(res["data"]["employees"]) > 0

    # Search by status
    res = tools.search_employees(status="active")
    assert res["success"] is True
    assert all(e["status"] == "active" for e in res["data"]["employees"])


def test_get_employee_profile(tools):
    # Valid employee ID
    res = tools.get_employee_profile(employee_id="NV001")
    assert res["success"] is True
    assert res["data"]["id"] == "NV001"
    assert res["data"]["name"] == "Nguyễn Văn A"
    assert res["data"]["department_name"] == "Phòng Kỹ thuật"

    # Non-existent employee ID
    res = tools.get_employee_profile(employee_id="NV999")
    assert res["success"] is False
    assert "Không tìm thấy" in res["error"]


def test_get_department_list(tools):
    res = tools.get_department_list()
    assert res["success"] is True
    departments = res["data"]["departments"]
    assert len(departments) >= 5
    dept_names = [d["name"] for d in departments]
    assert "Phòng Kỹ thuật" in dept_names
    assert "Phòng Nhân sự" in dept_names


def test_get_employee_department(tools):
    # By ID
    res = tools.get_employee_department(identifier="NV001")
    assert res["success"] is True
    assert res["data"]["department_name"] == "Phòng Kỹ thuật"
    assert res["data"]["employee_name"] == "Nguyễn Văn A"

    # By Name
    res = tools.get_employee_department(identifier="Nguyễn Văn A")
    assert res["success"] is True
    assert res["data"]["department_name"] == "Phòng Kỹ thuật"

    # Non-existent
    res = tools.get_employee_department(identifier="Người Không Tồn Tại")
    assert res["success"] is False


def test_get_employee_summary(tools):
    # Overall summary
    res = tools.get_employee_summary()
    assert res["success"] is True
    data = res["data"]
    assert data["total_employees"] >= 10
    assert data["active_count"] > 0
    assert "Phòng Kỹ thuật" in data["by_department"]

    # Filter by department
    res_tech = tools.get_employee_summary(department_id="DEP-TECH")
    assert res_tech["success"] is True
    assert res_tech["data"]["total_employees"] == 5
