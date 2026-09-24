"""Attendance MCP Tool implementations with validation and standard error handling."""

from typing import Any, Dict, Optional
from .function_support import AttendanceFunctionSupport, MockAttendanceSupport
from .schemas import ToolResponse
from .validators import validate_date, validate_employee_id, validate_month_year


class AttendanceTools:
    """Class containing all 5 Attendance MCP Tools and binding to function support."""

    def __init__(self, function_support: Optional[AttendanceFunctionSupport] = None):
        self.support = function_support or MockAttendanceSupport()

    def get_attendance_history(
        self,
        employee_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 30,
    ) -> Dict[str, Any]:
        """Get attendance history records for an employee within a date range."""
        valid, err = validate_employee_id(employee_id)
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        for d_str, field in [(from_date, "from_date"), (to_date, "to_date")]:
            v, e = validate_date(d_str, field)
            if not v:
                return ToolResponse(success=False, error=e).model_dump()

        try:
            records = self.support.get_attendance_history(
                employee_id=employee_id,
                from_date=from_date,
                to_date=to_date,
                limit=limit,
            )
            return ToolResponse(
                success=True,
                data={"employee_id": employee_id, "records": records, "total_records": len(records)},
            ).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi tra cứu lịch sử chuyên cần: {str(e)}").model_dump()

    def get_monthly_attendance(
        self,
        employee_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get monthly attendance summary (total work days, late days, absent days) for an employee."""
        valid, err = validate_employee_id(employee_id)
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        v_my, err_my = validate_month_year(month, year)
        if not v_my:
            return ToolResponse(success=False, error=err_my).model_dump()

        try:
            summary = self.support.get_monthly_attendance(employee_id=employee_id, month=month, year=year)
            if not summary:
                return ToolResponse(
                    success=False,
                    error=f"Không tìm thấy dữ liệu chuyên cần của nhân viên '{employee_id}' trong tháng {month}/{year}.",
                ).model_dump()
            return ToolResponse(success=True, data=summary).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi lấy dữ liệu chuyên cần tháng: {str(e)}").model_dump()

    def get_late_arrival_summary(
        self,
        employee_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get summary of late arrival incidents and total late minutes for an employee."""
        valid, err = validate_employee_id(employee_id)
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        v_my, err_my = validate_month_year(month, year)
        if not v_my:
            return ToolResponse(success=False, error=err_my).model_dump()

        try:
            summary = self.support.get_late_arrival_summary(employee_id=employee_id, month=month, year=year)
            return ToolResponse(success=True, data=summary).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi lấy dữ liệu đi trễ: {str(e)}").model_dump()

    def get_absence_summary(
        self,
        employee_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Get summary of absence days, paid and unpaid leaves for an employee."""
        valid, err = validate_employee_id(employee_id)
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        v_my, err_my = validate_month_year(month, year)
        if not v_my:
            return ToolResponse(success=False, error=err_my).model_dump()

        try:
            summary = self.support.get_absence_summary(employee_id=employee_id, month=month, year=year)
            return ToolResponse(success=True, data=summary).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi lấy dữ liệu vắng mặt: {str(e)}").model_dump()

    def get_attendance_statistics(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        department_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get company-wide or department attendance statistics."""
        try:
            stats = self.support.get_attendance_statistics(month=month, year=year, department_id=department_id)
            return ToolResponse(success=True, data=stats).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi lấy thống kê chuyên cần: {str(e)}").model_dump()
