"""Pydantic schemas for Employee MCP Server Tools and Responses."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolResponse(BaseModel):
    """Standardized response format for MCP Tools as required by system architecture."""
    success: bool = True
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=lambda: {"source": "employee"})


class Employee(BaseModel):
    """Schema representing an employee profile (safe fields, sensitive data masked)."""
    id: str
    name: str
    email: str
    phone: str
    department_id: str
    department_name: str
    position: str
    join_date: str
    status: str = "active"  # active, on_leave, resigned
    notes: Optional[str] = None


class Department(BaseModel):
    """Schema representing a company department."""
    id: str
    name: str
    code: str
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    member_count: int = 0
    description: Optional[str] = None


class EmployeeSummary(BaseModel):
    """Statistical summary of company workforce."""
    total_employees: int
    active_count: int
    on_leave_count: int
    resigned_count: int
    by_department: Dict[str, int]
    by_position: Dict[str, int]
