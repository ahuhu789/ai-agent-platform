"""
Unit tests cho AttendanceRepository (Phase 12, 13, 16).
Kiểm thử: Mock mode, Real mode (xử lý offline), Lookup theo codeDisplay và ID,
bảo toàn validation ATT-11 và ATT-12, xử lý file lỗi/thiếu.
Chạy 100% OFFLINE.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig
from integrations.my_enterprise_attendance.repository import AttendanceRepository


class TestAttendanceRepository:
    """Bộ kiểm thử cho AttendanceRepository."""

    def test_mock_mode_default_loads_data(self):
        config = MyEnterpriseConfig(data_source="mock")
        repo = AttendanceRepository(config)
        repo.load_data()

        # Kiểm tra nạp được nhân viên và bản ghi chấm công từ Web 1.18 crawl
        employees = repo.get_all_employees()
        records = repo.get_all_records()
        assert len(employees) >= 30
        assert len(records) > 0

        # Kiểm tra có mã My Enterprise (009, 001) và không có mã cũ E001
        assert "009" in employees
        assert "001" in employees
        assert "E001" not in employees

    def test_employee_lookup_by_code_and_id(self):
        repo = AttendanceRepository(MyEnterpriseConfig(data_source="mock"))

        # Tìm theo codeDisplay '009'
        emp_009 = repo.find_employee("009")
        assert emp_009 is not None
        assert "Vy" in emp_009["employee_name"]
        assert emp_009["employee_code"] == "009"

        # Tìm theo ID số 16 (ánh xạ nhân viên 009)
        emp_16 = repo.find_employee("16")
        assert emp_16 is not None
        assert emp_16["employee_code"] == "009"

        # Tìm theo mã 001 (Lê Thị Trà My)
        emp_001 = repo.find_employee("001")
        assert emp_001 is not None
        assert emp_001["employee_code"] == "001"

        # Tìm mã cũ E001 -> Không còn tồn tại
        assert repo.find_employee("E001") is None

        # Tìm mã không tồn tại
        assert repo.find_employee("NON_EXISTENT") is None

    def test_get_employee_attendance_mcp_output(self):
        repo = AttendanceRepository(MyEnterpriseConfig(data_source="mock"))
        res = repo.get_employee_attendance("009")
        assert res["success"] is True
        assert res["employee"]["employee_code"] == "009"
        assert "summary" in res
        assert "total_days_tracked" in res["summary"]
        assert "recent_records" in res

    def test_get_employee_attendance_zero_records_att13(self):
        repo = AttendanceRepository(MyEnterpriseConfig(data_source="mock"))
        # Nhân viên 000001 (Ngô Hoàng Tâm) tồn tại trong công ty nhưng chưa có bản ghi chấm công nào
        res = repo.get_employee_attendance("000001")
        assert res["success"] is True
        assert res["summary"]["total_days_tracked"] == 0
        assert "chưa có bản ghi" in res.get("message", "").lower()

    def test_get_attendance_history_att12_date_validation(self):
        repo = AttendanceRepository(MyEnterpriseConfig(data_source="mock"))

        # Hợp lệ
        res_ok = repo.get_attendance_history("009", "2026-08-01", "2026-08-15")
        assert res_ok["success"] is True
        assert res_ok["summary"]["total_days"] == 9

        # ATT-12: from_date > to_date
        res_err = repo.get_attendance_history("009", "2026-08-20", "2026-08-10")
        assert res_err["success"] is False
        assert "không hợp lệ" in res_err["error"].lower()

        # Định dạng sai
        res_fmt = repo.get_attendance_history("009", "2026/08/01", "2026-08-15")
        assert res_fmt["success"] is False

    def test_get_monthly_attendance_statistics_att11(self):
        repo = AttendanceRepository(MyEnterpriseConfig(data_source="mock"))

        # Hợp lệ: Tháng 9/2026 có 70 bản ghi
        res = repo.get_monthly_attendance_statistics(9, 2026)
        assert res["success"] is True
        assert res["company_summary"]["total_records"] >= 50
        assert "001" in res["employee_details"]
        assert "009" in res["employee_details"]

        # ATT-11: Tháng ngoài 1-12
        res_m = repo.get_monthly_attendance_statistics(13, 2026)
        assert res_m["success"] is False
        assert "tháng không hợp lệ" in res_m["error"].lower()

        # ATT-11: Năm ngoài 2000-2030
        res_y = repo.get_monthly_attendance_statistics(8, 1999)
        assert res_y["success"] is False
        assert "năm không hợp lệ" in res_y["error"].lower()

    def test_late_and_absence_summaries(self):
        repo = AttendanceRepository(MyEnterpriseConfig(data_source="mock"))

        res_late = repo.get_late_arrival_summary("009")
        assert res_late["success"] is True
        assert res_late["total_late_count"] >= 1

        res_abs = repo.get_absence_summary("009")
        assert res_abs["success"] is True
        assert "total_leave_approved" in res_abs
        assert "total_absent_unexcused" in res_abs

    @patch("integrations.my_enterprise_attendance.repository.EmployeeClient.get_all_employees")
    def test_real_mode_falls_back_when_offline_or_error(self, mock_emp):
        mock_emp.side_effect = Exception("VPN disconnected")

        config = MyEnterpriseConfig(data_source="real", token="token")
        repo = AttendanceRepository(config)
        repo.load_data()

        # Phải tự động fallback về mock data crawl, không được crash
        assert len(repo.get_all_employees()) > 0
