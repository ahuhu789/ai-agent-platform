"""Function Support interface and implementations for Employee subsystem."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import os
import urllib.request
import urllib.parse
import json

from .mock_data import MOCK_DEPARTMENTS, MOCK_EMPLOYEES


class EmployeeFunctionSupport(ABC):
    """Abstract interface for Employee module Function Support (FME)."""

    @abstractmethod
    def search_employees(
        self,
        keyword: Optional[str] = None,
        department_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_employee_profile(self, employee_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_department_list(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_employee_department(self, identifier: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_employee_summary(self, department_id: Optional[str] = None) -> Dict[str, Any]:
        raise NotImplementedError


class MockEmployeeSupport(EmployeeFunctionSupport):
    """In-memory Mock implementation of Employee Function Support."""

    def __init__(
        self,
        employees: Optional[List[Dict[str, Any]]] = None,
        departments: Optional[List[Dict[str, Any]]] = None,
    ):
        self.employees = list(employees if employees is not None else MOCK_EMPLOYEES)
        self.departments = list(departments if departments is not None else MOCK_DEPARTMENTS)

    def search_employees(
        self,
        keyword: Optional[str] = None,
        department_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        results = []
        kw = keyword.lower().strip() if keyword else None
        dept = department_id.upper().strip() if department_id else None
        st = status.lower().strip() if status else None

        for emp in self.employees:
            if st and emp.get("status", "").lower() != st:
                continue
            if dept and not (dept in emp.get("department_id", "").upper() or dept in emp.get("department_name", "").upper()):
                continue
            if kw:
                search_blob = f"{emp.get('id', '')} {emp.get('name', '')} {emp.get('position', '')} {emp.get('department_name', '')}".lower()
                if kw not in search_blob:
                    continue
            results.append(dict(emp))
            if len(results) >= limit:
                break
        return results

    def get_employee_profile(self, employee_id: str) -> Optional[Dict[str, Any]]:
        target_id = employee_id.strip().upper()
        for emp in self.employees:
            if emp.get("id", "").upper() == target_id:
                return dict(emp)
        return None

    def get_department_list(self) -> List[Dict[str, Any]]:
        return [dict(dept) for dept in self.departments]

    def get_employee_department(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Look up department for an employee by ID or Name."""
        target = identifier.strip().lower()
        # Direct search by ID or name
        for emp in self.employees:
            if emp.get("id", "").lower() == target or target in emp.get("name", "").lower():
                return {
                    "employee_id": emp.get("id"),
                    "employee_name": emp.get("name"),
                    "department_id": emp.get("department_id"),
                    "department_name": emp.get("department_name"),
                    "position": emp.get("position"),
                }
        return None

    def get_employee_summary(self, department_id: Optional[str] = None) -> Dict[str, Any]:
        filtered = self.employees
        if department_id:
            dept = department_id.upper().strip()
            filtered = [
                e for e in self.employees
                if dept in e.get("department_id", "").upper() or dept in e.get("department_name", "").upper()
            ]

        total = len(filtered)
        active = sum(1 for e in filtered if e.get("status") == "active")
        on_leave = sum(1 for e in filtered if e.get("status") == "on_leave")
        resigned = sum(1 for e in filtered if e.get("status") == "resigned")

        by_dept: Dict[str, int] = {}
        for e in filtered:
            d_name = e.get("department_name", "Khác")
            by_dept[d_name] = by_dept.get(d_name, 0) + 1

        by_pos: Dict[str, int] = {}
        for e in filtered:
            pos = e.get("position", "Khác")
            by_pos[pos] = by_pos.get(pos, 0) + 1

        return {
            "total_employees": total,
            "active_count": active,
            "on_leave_count": on_leave,
            "resigned_count": resigned,
            "by_department": by_dept,
            "by_position": by_pos,
        }


class RealEmployeeSupport(EmployeeFunctionSupport):
    """Production implementation connecting to the Employee REST API backend."""

    def __init__(self, api_url: Optional[str] = None, api_token: Optional[str] = None):
        self.api_url = (api_url or os.getenv("EMPLOYEE_API_URL", "http://localhost:8080/api/employee")).rstrip("/")
        self.api_token = api_token or os.getenv("EMPLOYEE_API_TOKEN", "")

    def _request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.api_url}/{endpoint.lstrip('/')}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            url = f"{url}?{query}"

        headers = {"Accept": "application/json"}
        if self.api_token:
            headers["Authorization"] = f"Bearer {self.api_token}"

        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def search_employees(
        self,
        keyword: Optional[str] = None,
        department_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        res = self._request("employees/search", {"keyword": keyword, "department_id": department_id, "status": status, "limit": limit})
        return res.get("data", [])

    def get_employee_profile(self, employee_id: str) -> Optional[Dict[str, Any]]:
        res = self._request(f"employees/{employee_id}")
        return res.get("data")

    def get_department_list(self) -> List[Dict[str, Any]]:
        res = self._request("departments")
        return res.get("data", [])

    def get_employee_department(self, identifier: str) -> Optional[Dict[str, Any]]:
        res = self._request("employees/department", {"identifier": identifier})
        return res.get("data")

    def get_employee_summary(self, department_id: Optional[str] = None) -> Dict[str, Any]:
        res = self._request("employees/summary", {"department_id": department_id})
        return res.get("data", {})
