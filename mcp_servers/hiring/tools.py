"""Hiring MCP Tool implementations with validation and standard error handling."""

from typing import Any, Dict, Optional
from .function_support import HiringFunctionSupport, MockHiringSupport
from .schemas import ToolResponse
from .validators import (
    validate_candidate_id,
    validate_candidate_status,
    validate_date,
    validate_job_status,
)


class HiringTools:
    """Class containing all 5 Hiring MCP Tools and binding to function support."""

    def __init__(self, function_support: Optional[HiringFunctionSupport] = None):
        self.support = function_support or MockHiringSupport()

    def search_candidates(
        self,
        keyword: Optional[str] = None,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Search candidates by keyword, status, or job ID."""
        valid, err = validate_candidate_status(status)
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        try:
            candidates = self.support.search_candidates(
                keyword=keyword,
                status=status,
                job_id=job_id,
                limit=limit,
            )
            return ToolResponse(
                success=True,
                data={"candidates": candidates, "total_found": len(candidates)},
            ).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi tìm kiếm ứng viên: {str(e)}").model_dump()

    def get_candidate_detail(self, candidate_id: str) -> Dict[str, Any]:
        """Get detailed profile of a candidate by their candidate ID."""
        valid, err = validate_candidate_id(candidate_id)
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        try:
            candidate = self.support.get_candidate_detail(candidate_id=candidate_id)
            if not candidate:
                return ToolResponse(
                    success=False,
                    error=f"Không tìm thấy ứng viên có mã '{candidate_id}'.",
                ).model_dump()

            return ToolResponse(success=True, data=candidate).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi tra cứu ứng viên: {str(e)}").model_dump()

    def list_job_openings(
        self,
        status: Optional[str] = "open",
        department: Optional[str] = None,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """List open or all job recruitment positions."""
        valid, err = validate_job_status(status)
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        try:
            jobs = self.support.list_job_openings(
                status=status,
                department=department,
                limit=limit,
            )
            return ToolResponse(
                success=True,
                data={"job_openings": jobs, "total_found": len(jobs)},
            ).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi lấy danh sách vị trí tuyển dụng: {str(e)}").model_dump()

    def get_interview_schedule(
        self,
        candidate_id: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get interview schedules filtered by candidate or date range (YYYY-MM-DD)."""
        valid, err = validate_date(from_date, "from_date")
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        valid, err = validate_date(to_date, "to_date")
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        try:
            schedules = self.support.get_interview_schedule(
                candidate_id=candidate_id,
                from_date=from_date,
                to_date=to_date,
            )
            return ToolResponse(
                success=True,
                data={"schedules": schedules, "total_found": len(schedules)},
            ).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi tra cứu lịch phỏng vấn: {str(e)}").model_dump()

    def get_recruitment_summary(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get high-level statistics and summary of recruitment metrics."""
        valid, err = validate_date(from_date, "from_date")
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        valid, err = validate_date(to_date, "to_date")
        if not valid:
            return ToolResponse(success=False, error=err).model_dump()

        try:
            summary = self.support.get_recruitment_summary(from_date=from_date, to_date=to_date)
            return ToolResponse(success=True, data=summary).model_dump()
        except Exception as e:
            return ToolResponse(success=False, error=f"Lỗi khi tổng hợp báo cáo tuyển dụng: {str(e)}").model_dump()
