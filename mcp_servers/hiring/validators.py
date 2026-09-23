"""Input validation functions for Hiring MCP Tools."""

import re
from datetime import datetime
from typing import Optional, Tuple

VALID_CANDIDATE_STATUSES = {
    "applied",
    "screening",
    "pending_interview",
    "interviewing",
    "offered",
    "rejected",
    "hired",
}

VALID_JOB_STATUSES = {"open", "closed", "paused"}


def validate_date(date_str: Optional[str], field_name: str = "date") -> Tuple[bool, Optional[str]]:
    """Validate ISO date format YYYY-MM-DD."""
    if not date_str:
        return True, None
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True, None
    except ValueError:
        return False, f"Trường '{field_name}' không đúng định dạng YYYY-MM-DD (nhận được: '{date_str}')."


def validate_candidate_status(status: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate candidate status if provided."""
    if not status:
        return True, None
    status_lower = status.strip().lower()
    if status_lower not in VALID_CANDIDATE_STATUSES:
        valid_list = ", ".join(sorted(VALID_CANDIDATE_STATUSES))
        return False, f"Trạng thái ứng viên '{status}' không hợp lệ. Các trạng thái hợp lệ: {valid_list}."
    return True, None


def validate_job_status(status: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate job status if provided."""
    if not status:
        return True, None
    status_lower = status.strip().lower()
    if status_lower not in VALID_JOB_STATUSES:
        valid_list = ", ".join(sorted(VALID_JOB_STATUSES))
        return False, f"Trạng thái vị trí tuyển dụng '{status}' không hợp lệ. Các trạng thái hợp lệ: {valid_list}."
    return True, None


def validate_candidate_id(candidate_id: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Validate candidate ID is provided and non-empty."""
    if not candidate_id or not candidate_id.strip():
        return False, "Thiếu mã ứng viên (candidate_id) bắt buộc."
    return True, None
