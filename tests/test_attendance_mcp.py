"""Unit tests for Attendance MCP Server tools and validation."""

import pytest
from mcp_servers.attendance.function_support import MockAttendanceSupport
from mcp_servers.attendance.tools import AttendanceTools
from mcp_servers.attendance.validators import (
    validate_date,
    validate_employee_id,
    validate_month_year,
)


@pytest.fixture
def tools():
    return AttendanceTools(MockAttendanceSupport())


def test_attendance_validators():
    # Employee ID
    assert validate_employee_id("NV001")[0] is True
    assert validate_employee_id("")[0] is False
    assert validate_employee_id(None)[0] is False

    # Date
    assert validate_date("2026-09-01")[0] is True
    assert validate_date(None)[0] is True
    assert validate_date("invalid-date")[0] is False

    # Month Year
    assert validate_month_year(9, 2026)[0] is True
    assert validate_month_year(13, 2026)[0] is False
    assert validate_month_year(0, 2026)[0] is False
    assert validate_month_year(9, 1990)[0] is False


def test_get_attendance_history(tools):
    res = tools.get_attendance_history(employee_id="NV001", from_date="2026-09-01", to_date="2026-09-10")
    assert res["success"] is True
    assert res["metadata"]["source"] == "attendance"
    assert len(res["data"]["records"]) > 0


def test_get_monthly_attendance(tools):
    # NV001 in Sept 2026: exactly 18 actual working days
    res = tools.get_monthly_attendance(employee_id="NV001", month=9, year=2026)
    assert res["success"] is True
    data = res["data"]
    assert data["actual_working_days"] == 18
    assert data["employee_name"] == "Nguyễn Văn A"


def test_get_late_arrival_summary(tools):
    # NV001 in Sept 2026: exactly 2 late arrivals
    res = tools.get_late_arrival_summary(employee_id="NV001", month=9, year=2026)
    assert res["success"] is True
    data = res["data"]
    assert data["late_count"] == 2
    assert data["total_late_minutes"] == 35


def test_get_absence_summary(tools):
    res = tools.get_absence_summary(employee_id="NV001", month=9, year=2026)
    assert res["success"] is True
    assert res["data"]["absent_days"] == 1


def test_get_attendance_statistics(tools):
    res = tools.get_attendance_statistics(month=9, year=2026)
    assert res["success"] is True
    assert res["data"]["total_employees"] > 0
    assert "Phòng Kỹ thuật" in res["data"]["by_department"]
