"""Function Support interface and implementations for Attendance subsystem."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import os
import urllib.request
import urllib.parse
import json

from .mock_data import MOCK_ATTENDANCE_RECORDS, MOCK_MONTHLY_ATTENDANCE


class AttendanceFunctionSupport(ABC):
    """Abstract interface for Attendance module Function Support (FME)."""

    @abstractmethod
    def get_attendance_history(
        self,
        employee_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_monthly_attendance(
        self,
        employee_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_late_arrival_summary(
        self,
        employee_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_absence_summary(
        self,
        employee_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_attendance_statistics(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        department_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        raise NotImplementedError


class MockAttendanceSupport(AttendanceFunctionSupport):
    """In-memory Mock implementation of Attendance Function Support."""

    def __init__(
        self,
        records: Optional[List[Dict[str, Any]]] = None,
        monthly_map: Optional[Dict[tuple, Dict[str, Any]]] = None,
    ):
        self.records = list(records if records is not None else MOCK_ATTENDANCE_RECORDS)
        self.monthly_map = dict(monthly_map if monthly_map is not None else MOCK_MONTHLY_ATTENDANCE)

    def _resolve_employee_id(self, employee_id_or_name: str) -> str:
        """Resolve employee ID or name (like 'Nhân viên A' -> 'NV001', 'Đặng Mai K' -> 'NV010')."""
        target = (employee_id_or_name or "").strip()
        if not target:
            return ""
        if target.upper().startswith("NV"):
            return target.upper()
        if target.upper() in ("ALL", "HÔM NAY", "HOM NAY", "AI", "TOÀN BỘ", "TOAN BO", "TẤT CẢ", "TAT CA", "TOÀN CÔNG TY", "TOAN CONG TY"):
            return "ALL"

        target_lower = target.lower()

        # Letter lookup (A -> NV001, B -> NV002, ..., K -> NV010, L -> NV011)
        letter_map = {
            "a": "NV001", "b": "NV002", "c": "NV003", "d": "NV004",
            "e": "NV005", "f": "NV006", "g": "NV007", "h": "NV008",
            "i": "NV009", "k": "NV010", "l": "NV011"
        }
        for prefix in ("nhân viên ", "nhan vien ", "nv ", "nv"):
            if target_lower.startswith(prefix):
                suffix = target_lower[len(prefix):].strip()
                if suffix in letter_map:
                    return letter_map[suffix]

        if target_lower in letter_map:
            return letter_map[target_lower]

        # Match full or partial name against records & monthly_map
        for r in self.records:
            name = (r.get("employee_name") or "").lower()
            if name and (name in target_lower or target_lower in name):
                return r.get("employee_id", target)

        for (eid, _, _), m_data in self.monthly_map.items():
            name = (m_data.get("employee_name") or "").lower()
            if name and (name in target_lower or target_lower in name):
                return eid

        # Check ending letter (e.g. "nhân viên đặng mai k" ends with "k")
        words = target_lower.split()
        if words and words[-1] in letter_map:
            return letter_map[words[-1]]

        return target

    def get_attendance_history(
        self,
        employee_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        emp_id = self._resolve_employee_id(employee_id)
        results = []
        for r in self.records:
            if emp_id != "ALL" and r.get("employee_id") != emp_id:
                continue
            r_date = r.get("date", "")
            if from_date and r_date < from_date:
                continue
            if to_date and r_date > to_date:
                continue
            results.append(dict(r))
            if len(results) >= limit:
                break
        return results

    def get_monthly_attendance(
        self,
        employee_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        emp_id = self._resolve_employee_id(employee_id)
        m = month or 9
        y = year or 2026

        key = (emp_id, m, y)
        if key in self.monthly_map:
            return dict(self.monthly_map[key])

        # If not pre-aggregated, calculate from records
        emp_records = [
            r for r in self.records
            if r.get("employee_id") == emp_id and r.get("date", "").startswith(f"{y:04d}-{m:02d}")
        ]
        if not emp_records:
            # Default fallback for demonstration
            return {
                "employee_id": emp_id,
                "employee_name": f"Nhân viên {emp_id}",
                "month": m,
                "year": y,
                "total_working_days": 18,
                "actual_working_days": 18,
                "late_count": 0,
                "early_leave_count": 0,
                "absent_count": 0,
                "attendance_rate": 100.0,
            }

        worked = sum(1 for r in emp_records if r.get("status") in ("on_time", "late"))
        late = sum(1 for r in emp_records if r.get("status") == "late")
        absent = sum(1 for r in emp_records if r.get("status") == "absent")
        total = len(emp_records)
        rate = round((worked / total * 100), 1) if total > 0 else 100.0

        emp_name = emp_records[0].get("employee_name", f"Nhân viên {emp_id}")
        return {
            "employee_id": emp_id,
            "employee_name": emp_name,
            "month": m,
            "year": y,
            "total_working_days": total,
            "actual_working_days": worked,
            "late_count": late,
            "early_leave_count": 0,
            "absent_count": absent,
            "attendance_rate": rate,
        }

    def get_late_arrival_summary(
        self,
        employee_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        emp_id = self._resolve_employee_id(employee_id)
        m = month or 9
        y = year or 2026

        late_records = [
            r for r in self.records
            if (emp_id == "ALL" or r.get("employee_id") == emp_id)
            and r.get("status") == "late"
            and r.get("date", "").startswith(f"{y:04d}-{m:02d}")
        ]

        total_minutes = sum(r.get("late_minutes", 0) for r in late_records)
        emp_name = late_records[0].get("employee_name") if late_records else "Nhân viên"
        if emp_name == "Nhân viên" and (emp_id, m, y) in self.monthly_map:
            emp_name = self.monthly_map[(emp_id, m, y)]["employee_name"]

        return {
            "employee_id": emp_id,
            "employee_name": emp_name if emp_id != "ALL" else "Toàn bộ nhân viên",
            "month": m,
            "year": y,
            "late_count": len(late_records),
            "total_late_minutes": total_minutes,
            "details": [dict(r) for r in late_records],
        }

    def get_absence_summary(
        self,
        employee_id: str,
        month: Optional[int] = None,
        year: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        emp_id = self._resolve_employee_id(employee_id)
        m = month or 9
        y = year or 2026

        if emp_id == "ALL":
            absent_records = [
                r for r in self.records
                if r.get("status") == "absent"
                and r.get("date", "").startswith(f"{y:04d}-{m:02d}")
            ]
            return {
                "employee_id": "ALL",
                "employee_name": "Tất cả nhân viên",
                "month": m,
                "year": y,
                "absent_days": len(absent_records),
                "leave_with_permission": sum(1 for r in absent_records if "không phép" not in (r.get("notes") or "").lower()),
                "leave_without_permission": sum(1 for r in absent_records if "không phép" in (r.get("notes") or "").lower()),
                "details": [dict(r) for r in absent_records],
            }

        absent_records = [
            r for r in self.records
            if r.get("employee_id") == emp_id
            and r.get("status") == "absent"
            and r.get("date", "").startswith(f"{y:04d}-{m:02d}")
        ]

        emp_name = None
        if absent_records:
            emp_name = absent_records[0].get("employee_name")
        if not emp_name:
            for r in self.records:
                if r.get("employee_id") == emp_id and r.get("employee_name"):
                    emp_name = r.get("employee_name")
                    break
        if not emp_name and (emp_id, m, y) in self.monthly_map:
            emp_name = self.monthly_map[(emp_id, m, y)]["employee_name"]
        if not emp_name:
            emp_name = f"Nhân viên {emp_id}"

        absent_count = len(absent_records)
        if absent_count == 0 and (emp_id, m, y) in self.monthly_map:
            absent_count = self.monthly_map[(emp_id, m, y)].get("absent_count", 0)

        with_perm = sum(1 for r in absent_records if "không phép" not in (r.get("notes") or "").lower())
        without_perm = sum(1 for r in absent_records if "không phép" in (r.get("notes") or "").lower())
        if absent_count > 0 and len(absent_records) == 0:
            with_perm = absent_count
            without_perm = 0

        return {
            "employee_id": emp_id,
            "employee_name": emp_name,
            "month": m,
            "year": y,
            "absent_days": absent_count,
            "leave_with_permission": with_perm,
            "leave_without_permission": without_perm,
            "details": [dict(r) for r in absent_records],
        }

    def get_attendance_statistics(
        self,
        month: Optional[int] = None,
        year: Optional[int] = None,
        department_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        m = month or 9
        y = year or 2026
        if m == 8:
            return {
                "month": 8,
                "year": y,
                "total_employees": 10,
                "average_attendance_rate": 98.5,
                "total_late_incidents": 2,
                "total_absent_days": 1,
                "by_department": {
                    "Phòng Kỹ thuật": {"attendance_rate": 98.0, "late_incidents": 1, "absent_days": 1},
                    "Phòng Nhân sự": {"attendance_rate": 100.0, "late_incidents": 0, "absent_days": 0},
                    "Phòng Kế toán": {"attendance_rate": 99.0, "late_incidents": 1, "absent_days": 0},
                },
            }
        return {
            "month": m,
            "year": y,
            "total_employees": 10,
            "average_attendance_rate": 95.8,
            "total_late_incidents": 4,
            "total_absent_days": 2,
            "by_department": {
                "Phòng Kỹ thuật": {"attendance_rate": 96.2, "late_incidents": 2, "absent_days": 1},
                "Phòng Nhân sự": {"attendance_rate": 94.5, "late_incidents": 1, "absent_days": 1},
                "Phòng Kế toán": {"attendance_rate": 100.0, "late_incidents": 0, "absent_days": 0},
            },
        }


class RealAttendanceSupport(AttendanceFunctionSupport):
    """Production implementation connecting to the Attendance REST API backend."""

    def __init__(self, api_url: Optional[str] = None, api_token: Optional[str] = None):
        self.api_url = (api_url or os.getenv("ATTENDANCE_API_URL", "http://localhost:8080/api/attendance")).rstrip("/")
        self.api_token = api_token or os.getenv("ATTENDANCE_API_TOKEN", "")

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

    def get_attendance_history(self, employee_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None, limit: int = 30) -> List[Dict[str, Any]]:
        res = self._request("history", {"employee_id": employee_id, "from_date": from_date, "to_date": to_date, "limit": limit})
        return res.get("data", [])

    def get_monthly_attendance(self, employee_id: str, month: Optional[int] = None, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        res = self._request("monthly", {"employee_id": employee_id, "month": month, "year": year})
        return res.get("data")

    def get_late_arrival_summary(self, employee_id: str, month: Optional[int] = None, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        res = self._request("late-summary", {"employee_id": employee_id, "month": month, "year": year})
        return res.get("data")

    def get_absence_summary(self, employee_id: str, month: Optional[int] = None, year: Optional[int] = None) -> Optional[Dict[str, Any]]:
        res = self._request("absence-summary", {"employee_id": employee_id, "month": month, "year": year})
        return res.get("data")

    def get_attendance_statistics(self, month: Optional[int] = None, year: Optional[int] = None, department_id: Optional[str] = None) -> Dict[str, Any]:
        res = self._request("statistics", {"month": month, "year": year, "department_id": department_id})
        return res.get("data", {})
