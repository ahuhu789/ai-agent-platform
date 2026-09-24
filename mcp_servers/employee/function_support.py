"""Function Support interface and implementations for Employee subsystem."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import os
import urllib.request
import urllib.parse
import json
import unicodedata

from .mock_data import MOCK_DEPARTMENTS, MOCK_EMPLOYEES


def _strip_diacritics(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.replace("đ", "d").replace("Đ", "D")


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
                search_blob_no_dia = _strip_diacritics(search_blob)
                kw_no_dia = _strip_diacritics(kw)
                if kw not in search_blob and kw_no_dia not in search_blob_no_dia:
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
        """Look up department for an employee by ID or Name (supports both accented and unaccented)."""
        target = identifier.strip().lower()
        target_no_dia = _strip_diacritics(target)

        alias_map = {
            "a": "NV001", "nhan vien a": "NV001", "nv a": "NV001",
            "b": "NV002", "nhan vien b": "NV002", "nv b": "NV002",
            "c": "NV003", "nhan vien c": "NV003", "nv c": "NV003",
            "d": "NV004", "nhan vien d": "NV004", "nv d": "NV004",
            "e": "NV005", "nhan vien e": "NV005", "nv e": "NV005",
            "f": "NV006", "nhan vien f": "NV006", "nv f": "NV006",
            "g": "NV007", "nhan vien g": "NV007", "nv g": "NV007",
            "h": "NV008", "nhan vien h": "NV008", "nv h": "NV008",
            "i": "NV009", "nhan vien i": "NV009", "nv i": "NV009",
            "k": "NV010", "nhan vien k": "NV010", "nv k": "NV010",
        }
        resolved_id = alias_map.get(target_no_dia)

        # Direct search by ID or name
        for emp in self.employees:
            emp_id = emp.get("id", "").lower()
            emp_name = emp.get("name", "").lower()
            emp_name_no_dia = _strip_diacritics(emp_name)

            if (
                emp_id == target
                or (resolved_id and emp_id == resolved_id.lower())
                or target in emp_name
                or target_no_dia in emp_name_no_dia
            ):
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
