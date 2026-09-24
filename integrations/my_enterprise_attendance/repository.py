"""
Attendance Repository: Tầng trừu tượng hóa dữ liệu chuyên cần và nhân viên.
Kết nối giữa MCP Server và các nguồn dữ liệu (Mock Dataset hoặc Real API Crawl).

Đặc điểm kiến trúc:
- MCP Server KHÔNG gọi HTTP trực tiếp.
- Điều khiển chế độ qua ATTENDANCE_DATA_SOURCE: 'mock' (mặc định) hoặc 'real'.
- Tự động chuẩn hóa và ánh xạ định danh:
  employee_id (hệ thống) <-> employee_code (codeDisplay) <-> employee_name.
- Bảo toàn 100% các validation ATT-11 (tháng/năm) và ATT-12 (logic ngày).
- Ghi chú: Production attendance business rules require confirmation.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig
from integrations.my_enterprise_attendance.mapper import (
    normalize_employee,
    normalize_attendance_record,
    join_employee_attendance
)
from integrations.my_enterprise_attendance.employee_client import EmployeeClient, EmployeeClientError
from integrations.my_enterprise_attendance.attendance_client import AttendanceClient, AttendanceClientError

logger = logging.getLogger(__name__)

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(MODULE_DIR, "fixtures")
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, "..", ".."))
LOCAL_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "local")


class AttendanceRepository:
    """
    Repository cung cấp toàn bộ dữ liệu nghiệp vụ chuyên cần cho MCP Server.
    """

    def __init__(self, config: Optional[MyEnterpriseConfig] = None):
        self.config = config or MyEnterpriseConfig.from_env()
        self._employees: Dict[str, Dict[str, Any]] = {}
        self._attendance_records: List[Dict[str, Any]] = []
        self._is_loaded = False

    def load_data(self, force_reload: bool = False):
        """
        Nạp dữ liệu dựa trên cấu hình config.data_source ('mock' hoặc 'real').
        """
        if self._is_loaded and not force_reload:
            return

        self._is_loaded = True
        if self.config.data_source == "real":
            self._load_from_real_api()
        else:
            self._load_from_mock_data()

    def _load_from_mock_data(self):
        """
        Nạp dữ liệu từ data/mock/ (crawl Web 1.18) hoặc fixtures dự phòng.
        """
        self._employees = {}
        self._attendance_records = []

        emp_fixture = os.path.join(FIXTURES_DIR, "employees_mock.json")
        att_fixture = os.path.join(FIXTURES_DIR, "attendance_mock.json")
        mock_emp_path = os.path.join(PROJECT_ROOT, "data", "mock", "employees.json")

        raw_employees: List[Dict[str, Any]] = []
        raw_attendances: List[Dict[str, Any]] = []

        # 1. Ưu tiên nạp từ data/mock/employees.json (crawl thực tế), sau đó đến fixtures
        if os.path.exists(mock_emp_path):
            try:
                with open(mock_emp_path, "r", encoding="utf-8") as f:
                    loaded_mock = json.load(f)
                    if isinstance(loaded_mock, list) and len(loaded_mock) > 0:
                        raw_employees = loaded_mock
            except Exception as e:
                logger.error(f"Lỗi đọc data/mock/employees.json: {e}")

        if not raw_employees and os.path.exists(emp_fixture):
            try:
                with open(emp_fixture, "r", encoding="utf-8") as f:
                    raw_employees = json.load(f)
            except Exception as e:
                logger.error(f"Lỗi đọc employees_mock.json: {e}")

        mock_att_path = os.path.join(PROJECT_ROOT, "data", "mock", "attendance.json")
        if os.path.exists(mock_att_path):
            try:
                with open(mock_att_path, "r", encoding="utf-8") as f:
                    loaded_att = json.load(f)
                    if isinstance(loaded_att, list) and len(loaded_att) > 0:
                        raw_attendances = loaded_att
            except Exception as e:
                logger.error(f"Lỗi đọc data/mock/attendance.json: {e}")

        if not raw_attendances and os.path.exists(att_fixture):
            try:
                with open(att_fixture, "r", encoding="utf-8") as f:
                    raw_attendances = json.load(f)
            except Exception as e:
                logger.error(f"Lỗi đọc attendance_mock.json: {e}")

        # 2. Chuẩn hóa danh sách nhân viên
        for raw_emp in raw_employees:
            norm = normalize_employee(raw_emp)
            emp_code = norm.get("employee_code") or str(norm.get("employee_id"))
            emp_id_val = norm.get("employee_id") or raw_emp.get("id")
            # Lưu thêm department và position nếu có
            norm["position"] = raw_emp.get("position", "Nhân viên")
            norm["department"] = raw_emp.get("department", "Công ty")
            norm["id"] = emp_id_val
            norm["employee_id"] = emp_code
            norm["employee_code"] = emp_code

            # Khóa tra cứu chính theo codeDisplay (ví dụ: '009', 'E001')
            if emp_code:
                self._employees[emp_code.strip().upper()] = norm
            # Khóa tra cứu phụ theo id số (nếu khác codeDisplay)
            if emp_id_val is not None and str(emp_id_val).strip().upper() not in self._employees:
                self._employees[str(emp_id_val).strip().upper()] = norm

        # 4. Chuẩn hóa và JOIN các bản ghi attendance:
        # Nếu có attendance.employeeInfo.id -> JOIN: attendance.employeeInfo.id == employee.employee_id
        # Tuyệt đối không dùng tên để JOIN.
        for att in raw_attendances:
            if "employeeInfo" in att:
                norm_att = normalize_attendance_record(att)
            else:
                norm_att = dict(att)

            emp = None
            # Ưu tiên JOIN bằng ID số nếu có employeeInfo.id
            if isinstance(att.get("employeeInfo"), dict) and att["employeeInfo"].get("id") is not None:
                att_id_str = str(att["employeeInfo"]["id"]).strip().upper()
                emp = self._employees.get(att_id_str)
                if not emp:
                    for e in self._employees.values():
                        if str(e.get("employee_id", "")).strip().upper() == att_id_str or str(e.get("id", "")).strip().upper() == att_id_str:
                            emp = e
                            break

            if not emp:
                target_id = att.get("employee_id") or norm_att.get("employee_code") or norm_att.get("employee_id")
                target_key = str(target_id).strip().upper() if target_id else ""
                emp = self._employees.get(target_key)
                if not emp:
                    for e in self._employees.values():
                        if e.get("employee_code", "").upper() == target_key or str(e.get("employee_id", "")).upper() == target_key:
                            emp = e
                            break

            if emp:
                norm_att["employee_id"] = emp["employee_code"]
                norm_att["employee_code"] = emp["employee_code"]
                norm_att["employee_name"] = emp.get("employee_name") or emp.get("name")

            # Chuẩn hóa trạng thái nếu thiếu
            if not norm_att.get("status"):
                ci = norm_att.get("check_in")
                if ci:
                    ci_str = str(ci).strip()
                    if ci_str > "08:30:00" and not ci_str.startswith("00:"):
                        norm_att["status"] = "Late"
                        if not norm_att.get("notes"):
                            norm_att["notes"] = f"Đi muộn (Check-in: {ci_str[:5]})"
                    else:
                        norm_att["status"] = "Present"
                else:
                    norm_att["status"] = "Leave_Approved"

            self._attendance_records.append(norm_att)

    def _load_from_real_api(self):
        """
        Nạp dữ liệu từ Real API khi có VPN và token.
        Lưu raw snapshot vào data/local/ (không commit git).
        """
        try:
            emp_client = EmployeeClient(self.config)
            raw_employees = emp_client.get_all_employees()

            att_client = AttendanceClient(self.config)
            current_month = datetime.now().strftime("%Y-%m")
            raw_attendances = att_client.get_all_my_attendance(month_year=current_month)

            # Lưu cache an toàn
            os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
            with open(os.path.join(LOCAL_DATA_DIR, "employees_raw.json"), "w", encoding="utf-8") as f:
                json.dump(raw_employees, f, ensure_ascii=False, indent=2)
            with open(os.path.join(LOCAL_DATA_DIR, "attendance_raw.json"), "w", encoding="utf-8") as f:
                json.dump(raw_attendances, f, ensure_ascii=False, indent=2)

            # Thực hiện JOIN
            joined_records, mapped_count, unmapped_count = join_employee_attendance(raw_employees, raw_attendances)

            # Lưu normalized dataset
            with open(os.path.join(LOCAL_DATA_DIR, "attendance_normalized.json"), "w", encoding="utf-8") as f:
                json.dump(joined_records, f, ensure_ascii=False, indent=2)

            # Nạp vào memory
            self._employees = {}
            for emp in raw_employees:
                norm = normalize_employee(emp)
                emp_code = norm.get("employee_code") or str(norm.get("employee_id"))
                norm["employee_id"] = emp_code
                if emp_code:
                    self._employees[emp_code.strip().upper()] = norm

            self._attendance_records = joined_records

        except (EmployeeClientError, AttendanceClientError, Exception) as e:
            logger.warning(
                f"[REPOSITORY WARNING] Không thể kết nối Real API ({e}). "
                f"Tự động fallback về dữ liệu Mock offline."
            )
            self._load_from_mock_data()

    def find_employee(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Tìm kiếm nhân viên theo mã codeDisplay (ví dụ: '009', '001', '010') hoặc ID số.
        """
        if not query:
            return None
        self.load_data()
        q = str(query).strip().upper()
        # 1. Tìm trực tiếp
        if q in self._employees:
            return self._employees[q]
        # 2. Tìm theo employee_code hoặc employee_name
        for emp in self._employees.values():
            if emp.get("employee_code", "").upper() == q or str(emp.get("employee_id", "")).upper() == q:
                return emp
        return None

    def get_all_employees(self) -> Dict[str, Dict[str, Any]]:
        self.load_data()
        return dict(self._employees)

    def get_all_records(self) -> List[Dict[str, Any]]:
        self.load_data()
        return list(self._attendance_records)

    # =========================================================================
    # MCP TOOL METHODS (Chuẩn hóa tham số, kết quả và logic nghiệp vụ)
    # =========================================================================

    def get_employee_attendance(self, employee_id: str) -> Dict[str, Any]:
        """
        Lấy thông tin tổng quan và các bản ghi gần đây của một nhân viên.
        """
        self.load_data()
        emp_id = str(employee_id).strip().upper() if employee_id else ""
        employee = self.find_employee(emp_id)

        if not employee:
            return {"success": False, "error": f"Không tìm thấy nhân viên với mã {employee_id}"}

        target_code = str(employee.get("employee_code") or employee.get("employee_id") or "").strip().upper()
        records = [
            rec for rec in self._attendance_records
            if str(rec.get("employee_id") or "").strip().upper() == target_code
            or str(rec.get("employee_code") or "").strip().upper() == target_code
        ]

        all_system_dates = sorted(list(set([str(r.get("date", "")).strip() for r in self._attendance_records if r.get("date")])))
        emp_dates = set([str(r.get("date", "")).strip() for r in records if r.get("date")])
        unrecorded_dates = sorted([d for d in all_system_dates if d not in emp_dates])

        present_days = sum(1 for r in records if r.get("status") == "Present")
        late_days = sum(1 for r in records if r.get("status") == "Late")
        leave_days = sum(1 for r in records if r.get("status") == "Leave_Approved")
        absent_days = sum(1 for r in records if r.get("status") == "Absent_Unexcused")

        summary = {
            "total_days_tracked": len(records),
            "total_system_days": len(all_system_dates),
            "total_days_worked": present_days + late_days,
            "days_without_checkin": len(unrecorded_dates),
            "unrecorded_dates": unrecorded_dates,
            "present": present_days,
            "late": late_days,
            "leave_approved": leave_days,
            "absent_unexcused": absent_days
        }

        records.sort(key=lambda x: str(x.get("date", "")), reverse=True)
        recent_records = records[:5]

        # Đảm bảo trường name cho tương thích ngược
        emp_display = dict(employee)
        if "name" not in emp_display and emp_display.get("employee_name"):
            emp_display["name"] = emp_display["employee_name"]

        # Lấy danh sách tất cả các bản ghi đi muộn và vắng phép để phục vụ trả lời trọng tâm
        late_records = [r for r in records if r.get("status") == "Late"]
        late_records.sort(key=lambda x: str(x.get("date", "")))

        leave_records = [r for r in records if r.get("status") in ("Leave_Approved", "Absent_Unexcused")]
        leave_records.sort(key=lambda x: str(x.get("date", "")))

        result = {
            "success": True,
            "employee": emp_display,
            "summary": summary,
            "recent_records": recent_records,
            "late_records": late_records,
            "leave_records": leave_records,
            "unrecorded_dates": unrecorded_dates
        }
        if len(records) == 0:
            result["message"] = f"Nhân viên {emp_display.get('name')} ({target_code}) chưa có bản ghi chấm công nào trong hệ thống."

        return result

    def get_attendance_history(self, employee_id: str, from_date: str, to_date: str) -> Dict[str, Any]:
        """
        Lấy lịch sử chấm công của nhân viên theo khoảng ngày (Bảo toàn ATT-12).
        """
        self.load_data()
        emp_id = str(employee_id).strip().upper() if employee_id else ""
        employee = self.find_employee(emp_id)

        if not employee:
            return {"success": False, "error": f"Không tìm thấy nhân viên với mã {employee_id}"}

        if not from_date or not to_date:
            return {"success": False, "error": "Vui lòng cung cấp đầy đủ from_date và to_date (định dạng YYYY-MM-DD)."}

        try:
            start_dt = datetime.strptime(str(from_date).strip(), "%Y-%m-%d")
            end_dt = datetime.strptime(str(to_date).strip(), "%Y-%m-%d")
        except ValueError as ve:
            return {"success": False, "error": f"Định dạng hoặc giá trị ngày không hợp lệ (yêu cầu YYYY-MM-DD): {ve}"}

        # ATT-12: Kiểm tra start_dt <= end_dt
        if start_dt > end_dt:
            return {"success": False, "error": f"Khoảng thời gian không hợp lệ: ngày bắt đầu ({from_date}) không được lớn hơn ngày kết thúc ({to_date})."}

        target_code = str(employee.get("employee_code") or employee.get("employee_id") or "").strip().upper()
        records = []
        for rec in self._attendance_records:
            r_code = str(rec.get("employee_id") or "").strip().upper()
            r_emp_code = str(rec.get("employee_code") or "").strip().upper()
            if r_code == target_code or r_emp_code == target_code:
                try:
                    rec_dt = datetime.strptime(str(rec.get("date", "")).strip(), "%Y-%m-%d")
                    if start_dt <= rec_dt <= end_dt:
                        records.append(rec)
                except ValueError:
                    continue

        records.sort(key=lambda x: str(x.get("date", "")))

        p_days = sum(1 for r in records if r.get("status") == "Present")
        l_days = sum(1 for r in records if r.get("status") == "Late")

        summary = {
            "total_days": len(records),
            "total_days_worked": p_days + l_days,
            "present": p_days,
            "late": l_days,
            "leave_approved": sum(1 for r in records if r.get("status") == "Leave_Approved"),
            "absent_unexcused": sum(1 for r in records if r.get("status") == "Absent_Unexcused")
        }

        emp_display = dict(employee)
        if "name" not in emp_display and emp_display.get("employee_name"):
            emp_display["name"] = emp_display["employee_name"]

        return {
            "success": True,
            "employee": emp_display,
            "from_date": from_date,
            "to_date": to_date,
            "summary": summary,
            "records": records
        }

    def get_monthly_attendance_statistics(self, month: int, year: int) -> Dict[str, Any]:
        """
        Thống kê chấm công theo tháng và năm (Bảo toàn ATT-11).
        """
        self.load_data()
        try:
            month_int = int(month)
            year_int = int(year)
        except (ValueError, TypeError):
            return {"success": False, "error": f"Tháng hoặc năm không hợp lệ (phải là số nguyên): month={month}, year={year}"}

        # ATT-11: Validate month (1-12)
        if month_int < 1 or month_int > 12:
            return {"success": False, "error": f"Tháng không hợp lệ: {month}. Tháng phải nằm trong khoảng từ 1 đến 12."}

        # ATT-11: Validate year (2000-2030)
        if year_int < 2000 or year_int > 2030:
            return {"success": False, "error": f"Năm không hợp lệ: {year}. Năm phải nằm trong khoảng từ 2000 đến 2030."}

        prefix = f"{year_int:04d}-{month_int:02d}-"
        monthly_records = [
            rec for rec in self._attendance_records
            if str(rec.get("date", "")).startswith(prefix)
        ]

        if not monthly_records:
            return {"success": True, "statistics": {}, "message": f"Không có dữ liệu chấm công cho tháng {month_int}/{year_int}"}

        stats = {
            "total_records": len(monthly_records),
            "present": sum(1 for r in monthly_records if r.get("status") == "Present"),
            "late": sum(1 for r in monthly_records if r.get("status") == "Late"),
            "leave_approved": sum(1 for r in monthly_records if r.get("status") == "Leave_Approved"),
            "absent_unexcused": sum(1 for r in monthly_records if r.get("status") == "Absent_Unexcused")
        }

        employee_stats = {}
        all_emp_dicts = list(self._employees.values())

        for emp_info in all_emp_dicts:
            emp_code = str(emp_info.get("employee_code") or emp_info.get("employee_id") or "").strip().upper()
            if not emp_code or emp_code in employee_stats:
                continue
            emp_recs = [
                r for r in monthly_records
                if str(r.get("employee_id") or "").strip().upper() == emp_code
                or str(r.get("employee_code") or "").strip().upper() == emp_code
            ]
            if emp_recs:
                employee_stats[emp_code] = {
                    "name": emp_info.get("employee_name") or emp_info.get("name"),
                    "department": emp_info.get("department", "Công ty"),
                    "position": emp_info.get("position", "Nhân viên"),
                    "summary": {
                        "total_days": len(emp_recs),
                        "present": sum(1 for r in emp_recs if r.get("status") == "Present"),
                        "late": sum(1 for r in emp_recs if r.get("status") == "Late"),
                        "leave_approved": sum(1 for r in emp_recs if r.get("status") == "Leave_Approved"),
                        "absent_unexcused": sum(1 for r in emp_recs if r.get("status") == "Absent_Unexcused")
                    }
                }

        return {
            "success": True,
            "month": month_int,
            "year": year_int,
            "company_summary": stats,
            "employee_details": employee_stats
        }

    def get_late_arrival_summary(self, employee_id: str) -> Dict[str, Any]:
        """
        Thống kê chi tiết các lần đi muộn của nhân viên.
        """
        emp_att = self.get_employee_attendance(employee_id)
        if not emp_att.get("success"):
            return emp_att

        target_code = str(emp_att["employee"].get("employee_code") or emp_att["employee"].get("employee_id") or "").strip().upper()
        late_records = [
            r for r in self._attendance_records
            if (str(r.get("employee_id") or "").strip().upper() == target_code or
                str(r.get("employee_code") or "").strip().upper() == target_code)
            and r.get("status") == "Late"
        ]
        late_records.sort(key=lambda x: str(x.get("date", "")), reverse=True)

        return {
            "success": True,
            "employee": emp_att["employee"],
            "total_late_count": len(late_records),
            "late_records": late_records
        }

    def get_absence_summary(self, employee_id: str) -> Dict[str, Any]:
        """
        Thống kê chi tiết các ngày vắng có phép và không phép của nhân viên.
        """
        emp_att = self.get_employee_attendance(employee_id)
        if not emp_att.get("success"):
            return emp_att

        target_code = str(emp_att["employee"].get("employee_code") or emp_att["employee"].get("employee_id") or "").strip().upper()
        leave_approved = [
            r for r in self._attendance_records
            if (str(r.get("employee_id") or "").strip().upper() == target_code or
                str(r.get("employee_code") or "").strip().upper() == target_code)
            and r.get("status") == "Leave_Approved"
        ]
        absent_unexcused = [
            r for r in self._attendance_records
            if (str(r.get("employee_id") or "").strip().upper() == target_code or
                str(r.get("employee_code") or "").strip().upper() == target_code)
            and r.get("status") == "Absent_Unexcused"
        ]

        all_system_dates = sorted(list(set([str(r.get("date", "")).strip() for r in self._attendance_records if r.get("date")])))
        emp_all_dates = set([
            str(r.get("date", "")).strip() for r in self._attendance_records
            if (str(r.get("employee_id") or "").strip().upper() == target_code or
                str(r.get("employee_code") or "").strip().upper() == target_code)
            and r.get("date")
        ])
        unrecorded_dates = sorted([d for d in all_system_dates if d not in emp_all_dates])

        return {
            "success": True,
            "employee": emp_att["employee"],
            "total_leave_approved": len(leave_approved),
            "total_absent_unexcused": len(absent_unexcused),
            "days_without_checkin": len(unrecorded_dates),
            "total_system_days": len(all_system_dates),
            "unrecorded_dates": unrecorded_dates,
            "leave_approved_records": leave_approved,
            "absent_unexcused_records": absent_unexcused
        }

    def get_employee_list(self) -> Dict[str, Any]:
        """
        Lấy danh sách tất cả nhân viên trong công ty.
        """
        self.load_data()
        unique_employees = {}
        for emp_key, emp_info in self._employees.items():
            code = emp_info.get("employee_code") or emp_info.get("employee_id") or emp_key
            code = str(code).strip().upper()
            if code not in unique_employees:
                unique_employees[code] = {
                    "employee_id": code,
                    "name": emp_info.get("name") or emp_info.get("employee_name", "N/A"),
                    "position": emp_info.get("position", "Nhân viên"),
                    "department": emp_info.get("department", "Công ty")
                }

        emp_list = list(unique_employees.values())
        emp_list.sort(key=lambda x: x["employee_id"])

        return {
            "success": True,
            "total_employees": len(emp_list),
            "employees": emp_list
        }

    def get_latest_attendance_date(self) -> str:
        """
        Lấy ngày có bản ghi chấm công mới nhất trong hệ thống.
        """
        self.load_data()
        all_dates = sorted([str(r.get("date", "")).strip() for r in self._attendance_records if r.get("date")])
        return all_dates[-1] if all_dates else "2026-09-12"

    def get_daily_attendance(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Lấy thông tin chấm công của tất cả nhân viên công ty trong một ngày cụ thể.
        Nếu target_date rỗng, None hoặc 'hôm nay': Mặc định lấy ngày hôm nay thực tế.
        """
        self.load_data()
        today_str = datetime.now().strftime("%Y-%m-%d")

        if not target_date or str(target_date).strip().lower() in ("hôm nay", "today", "null", "none", ""):
            query_date = today_str
        elif str(target_date).strip().lower() in ("hôm qua", "yesterday"):
            query_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            query_date = str(target_date).strip()

        day_records = [
            r for r in self._attendance_records
            if str(r.get("date", "")).strip() == query_date
        ]

        emp_list_res = self.get_employee_list()
        all_emps = {e["employee_id"]: e for e in emp_list_res["employees"]}

        present_list = []
        late_list = []
        leave_approved_list = []
        absent_unexcused_list = []

        seen_eids = set()
        for rec in day_records:
            eid = str(rec.get("employee_id") or rec.get("employee_code", "")).strip().upper()
            seen_eids.add(eid)
            emp_info = all_emps.get(eid, {})
            name = emp_info.get("name") or rec.get("employee_name", "N/A")
            dept = emp_info.get("department", "Công ty")
            pos = emp_info.get("position", "Nhân viên")

            item = {
                "employee_id": eid,
                "name": name,
                "department": dept,
                "position": pos,
                "status": rec.get("status"),
                "check_in": rec.get("check_in"),
                "check_out": rec.get("check_out"),
                "notes": rec.get("notes", "")
            }

            if rec.get("status") == "Present":
                present_list.append(item)
            elif rec.get("status") == "Late":
                late_list.append(item)
            elif rec.get("status") == "Leave_Approved":
                leave_approved_list.append(item)
            elif rec.get("status") == "Absent_Unexcused":
                absent_unexcused_list.append(item)

        unrecorded_list = []
        for eid, e_info in all_emps.items():
            if eid not in seen_eids:
                unrecorded_list.append({
                    "employee_id": eid,
                    "name": e_info["name"],
                    "department": e_info["department"],
                    "position": e_info["position"],
                    "status": "Unrecorded",
                    "notes": "Chưa có bản ghi chấm công trong ngày"
                })

        total_working = len(present_list) + len(late_list)
        total_absent = len(leave_approved_list) + len(absent_unexcused_list)

        return {
            "success": True,
            "date": query_date,
            "summary": {
                "total_employees": len(all_emps),
                "total_working": total_working,
                "present_on_time": len(present_list),
                "late": len(late_list),
                "total_absent": total_absent,
                "leave_approved": len(leave_approved_list),
                "absent_unexcused": len(absent_unexcused_list),
                "unrecorded": len(unrecorded_list)
            },
            "working_employees": present_list + late_list,
            "absent_employees": leave_approved_list + absent_unexcused_list,
            "unrecorded_employees": unrecorded_list
        }


# Singleton pattern
_GLOBAL_REPOSITORY: Optional[AttendanceRepository] = None

def get_repository() -> AttendanceRepository:
    global _GLOBAL_REPOSITORY
    if _GLOBAL_REPOSITORY is None:
        _GLOBAL_REPOSITORY = AttendanceRepository()
    return _GLOBAL_REPOSITORY
