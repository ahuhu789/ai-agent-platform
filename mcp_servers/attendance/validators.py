"""Input validation functions for Attendance MCP Tools."""

from datetime import datetime
from typing import Optional, Tuple


def validate_employee_id(employee_id: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate that employee_id is provided and non-empty."""
    if not employee_id or not employee_id.strip():
        return False, "Thiếu mã nhân viên (employee_id) bắt buộc."
    return True, None


def validate_date(date_str: Optional[str], field_name: str = "date") -> Tuple[bool, Optional[str]]:
    """Validate ISO date format YYYY-MM-DD."""
    if not date_str:
        return True, None
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True, None
    except ValueError:
        return False, f"Trường '{field_name}' không đúng định dạng YYYY-MM-DD (nhận được: '{date_str}')."


def validate_month_year(month: Optional[int], year: Optional[int]) -> Tuple[bool, Optional[str]]:
    """Validate month (1-12) and year (> 2000)."""
    if month is not None:
        if not (1 <= month <= 12):
            return False, f"Tháng phải nằm trong khoảng từ 1 đến 12 (nhận được: {month})."
    if year is not None:
        if year < 2000 or year > 2100:
            return False, f"Năm không hợp lệ (nhận được: {year})."
    return True, None
