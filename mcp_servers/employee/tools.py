"""Employee MCP Tool implementations with validation and standard error handling."""

from typing import Any, Dict, Optional
from .function_support import EmployeeFunctionSupport, MockEmployeeSupport
from .schemas import ToolResponse
from .validators import (
    validate_department_id,
    validate_employee_id,
    validate_employee_status,
)


class EmployeeTools:
    """Class containing all 5 Employee MCP Tools and binding to function support."""

    def __init__(self, function_support: Optional[EmployeeFunctionSupport] = None):
        self.support = function_support or MockEmployeeSupport()

    def search_employees(
        self,
        keyword: Optional[str] = None,
        department_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search employees by keyword, department, or status."""
        valid, err = validate_employee_status(status)
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        try:
            employees = self.support.search_employees(
                keyword=keyword,
                department_id=department_id,
                status=status,
                limit=limit,
            )
            return ToolResponse(
                success=True,
                data={"employees": employees, "total_found": len(employees)},
            ).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi tìm kiếm nhân viên: {str(e)}").model_dump()

    def get_employee_profile(self, employee_id: str) -> Dict[str, Any]:
        """Get detailed profile of an employee by their employee ID."""
        valid, err = validate_employee_id(employee_id)
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        try:
            profile = self.support.get_employee_profile(employee_id=employee_id)
            if not profile:
                return ToolResponse(
                    success=False,
                    error=f"Không tìm thấy nhân viên có mã '{employee_id}'.",
                ).model_dump()

            return ToolResponse(success=True, data=profile).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi tra cứu hồ sơ nhân viên: {str(e)}").model_dump()

    def get_department_list(self) -> Dict[str, Any]:
        """List all company departments and their manager details."""
        try:
            departments = self.support.get_department_list()
            return ToolResponse(
                success=True,
                data={"departments": departments, "total_departments": len(departments)},
            ).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi lấy danh sách phòng ban: {str(e)}").model_dump()

    def get_employee_department(self, identifier: str) -> Dict[str, Any]:
        """Find which department an employee belongs to by ID or Name."""
        if not identifier or not identifier.strip():
            return ToolResponse(success=False, error="Vui lòng cung cấp mã hoặc tên nhân viên cần tra cứu phòng ban.").model_dump()

        try:
            result = self.support.get_employee_department(identifier=identifier)
            if not result:
                return ToolResponse(
                    success=False,
                    error=f"Không tìm thấy thông tin phòng ban của nhân viên '{identifier}'.",
                ).model_dump()

            return ToolResponse(success=True, data=result).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi tra cứu phòng ban nhân viên: {str(e)}").model_dump()

    def get_employee_summary(self, department_id: Optional[str] = None) -> Dict[str, Any]:
        """Get workforce statistics across company or for a specific department."""
        try:
            summary = self.support.get_employee_summary(department_id=department_id)
            return ToolResponse(success=True, data=summary).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi lấy thống kê nhân sự: {str(e)}").model_dump()
