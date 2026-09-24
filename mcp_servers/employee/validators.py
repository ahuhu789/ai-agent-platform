"""Input validation functions for Employee MCP Tools."""

from typing import Optional, Tuple

VALID_EMPLOYEE_STATUSES = {"active", "on_leave", "resigned"}


def validate_employee_id(employee_id: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate that employee_id is provided and not empty."""
    if not employee_id or not employee_id.strip():
        return False, "Thiếu mã nhân viên (employee_id) bắt buộc."
    return True, None


def validate_department_id(department_id: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate department_id if provided."""
    if not department_id or not department_id.strip():
        return False, "Thiếu mã hoặc tên phòng ban (department_id) bắt buộc."
    return True, None


def validate_employee_status(status: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate employee status if provided."""
    if not status:
        return True, None
    status_lower = status.strip().lower()
    if status_lower not in VALID_EMPLOYEE_STATUSES:
        valid_list = ", ".join(sorted(VALID_EMPLOYEE_STATUSES))
        return False, f"Trạng thái nhân viên '{status}' không hợp lệ. Các trạng thái hợp lệ: {valid_list}."
    return True, None
