"""Pydantic schemas for Hiring MCP Server Tools and Responses."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """Standardized response format for MCP Tools as required by system architecture."""
    success: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"source": "hiring"})


class Candidate(BaseModel):
    id: str
    name: str
    email: str
    phone: str
    position: str
    job_id: str
    status: str  # applied, screening, pending_interview, interviewing, offered, rejected, hired
    experience_years: float
    skills: List[str]
    applied_date: str
    notes: Optional[str] = None


class JobOpening(BaseModel):
    id: str
    title: str
    department: str
    open_positions: int
    status: str  # open, closed, paused
    requirements: List[str]
    salary_range: str
    created_date: str


class InterviewSchedule(BaseModel):
    id: str
    candidate_id: str
    candidate_name: str
    job_title: str
    interview_date: str
    interview_time: str
    interviewer: str
    round: int
    status: str  # scheduled, completed, cancelled


class RecruitmentSummary(BaseModel):
    total_openings: int
    total_candidates: int
    pending_interview_count: int
    interviewing_count: int
    offered_count: int
    rejected_count: int
    hired_count: int
    by_department: Dict[str, int]
    by_status: Dict[str, int]
