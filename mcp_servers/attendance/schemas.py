"""Pydantic schemas for Attendance MCP Server Tools and Responses."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """Standardized response format for MCP Tools as required by system architecture."""
    success: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"source": "attendance"})


class AttendanceRecord(BaseModel):
    """Daily check-in / check-out attendance record."""
    id: str
    employee_id: str
    employee_name: str
    date: str  # YYYY-MM-DD
    check_in: Optional[str] = None  # HH:MM:SS
    check_out: Optional[str] = None  # HH:MM:SS
    status: str = "on_time"  # on_time, late, early_leave, absent, holiday
    work_hours: float = 8.0
    late_minutes: int = 0
    notes: Optional[str] = None


class MonthlyAttendance(BaseModel):
    """Monthly attendance aggregation for an employee."""
    employee_id: str
    employee_name: str
    month: int
    year: int
    total_working_days: int
    actual_working_days: int
    late_count: int
    early_leave_count: int
    absent_count: int
    attendance_rate: float


class LateArrivalSummary(BaseModel):
    """Summary of late arrival infractions for an employee."""
    employee_id: str
    employee_name: str
    month: int
    year: int
    late_count: int
    total_late_minutes: int
    details: List[Dict[str, Any]] = Field(default_factory=list)


class AbsenceSummary(BaseModel):
    """Summary of employee absences and leaves."""
    employee_id: str
    employee_name: str
    month: int
    year: int
    absent_days: int
    leave_with_permission: int
    leave_without_permission: int
    details: List[Dict[str, Any]] = Field(default_factory=list)


class AttendanceStatistics(BaseModel):
    """High level statistics for company or department."""
    month: int
    year: int
    total_employees: int
    average_attendance_rate: float
    total_late_incidents: int
    total_absent_days: int
    by_department: Dict[str, Any] = Field(default_factory=dict)
