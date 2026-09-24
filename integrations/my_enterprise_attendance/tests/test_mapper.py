"""
Unit tests cho Mapper và JOIN Logic (Phase 4, Phase 7, Phase 8, Phase 16).
Kiểm thử tính đúng đắn của mapping trường, ưu tiên codeDisplay, an toàn với null,
và JOIN bằng Employee.id == Attendance.employeeInfo.id.
"""

import os
import sys
import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from integrations.my_enterprise_attendance.mapper import (
    normalize_employee,
    normalize_attendance_record,
    normalize_attendance_response,
    join_employee_attendance,
    _extract_full_name
)


class TestMapper:
    """Bộ kiểm thử cho Mapper & JOIN."""

    def test_normalize_employee_fields(self):
        raw = {
            "id": 1,
            "firstName": "Tâm",
            "lastName": "Ngô Hoàng",
            "codeDisplay": "000001"
        }
        norm = normalize_employee(raw)
        assert norm["employee_id"] == 1
        assert norm["employee_code"] == "000001"
        assert norm["first_name"] == "Tâm"
        assert norm["last_name"] == "Ngô Hoàng"
        assert norm["employee_name"] == "Ngô Hoàng Tâm"

    def test_codedisplay_used_as_employee_code_strictly(self):
        """
        QUAN TRỌNG:
        employee_code PHẢI lấy từ codeDisplay, KHÔNG lấy từ id.
        Ví dụ: id = 16, codeDisplay = '009' -> employee_code = '009' (KHÔNG PHẢI '16').
        """
        raw = {
            "id": 16,
            "firstName": "Vy",
            "lastName": "Lê Hữu Thanh",
            "codeDisplay": "009"
        }
        norm = normalize_employee(raw)
        assert norm["employee_code"] == "009"
        assert norm["employee_code"] != "16"
        assert norm["employee_code"] != 16
        assert norm["employee_id"] == 16

    def test_normalize_employee_null_safe(self):
        norm1 = normalize_employee(None)
        assert norm1["employee_id"] is None
        assert norm1["employee_code"] is None
        assert norm1["employee_name"] is None

        norm2 = normalize_employee({})
        assert norm2["employee_id"] is None
        assert norm2["employee_code"] is None
        assert norm2["employee_name"] is None

    def test_normalize_attendance_record_fields(self):
        raw = {
            "employeeInfo": {
                "id": 16,
                "firstName": "Vy",
                "lastName": "Lê Hữu Thanh",
                "codeDisplay": "009"
            },
            "recordDate": "2026-09-04",
            "recordTime": "10:19:49",
            "checkInTime": "10:19:49",
            "checkOutTime": "21:19:57",
            "latitude": 10.807207964,
            "longitude": 106.628620666,
            "locationName": "Phường Tân Sơn Nhì, Tân Phú, TP.HCM"
        }
        norm = normalize_attendance_record(raw)
        assert norm["employee_id"] == 16
        assert norm["employee_code"] == "009"
        assert norm["employee_name"] == "Lê Hữu Thanh Vy"
        assert norm["date"] == "2026-09-04"
        assert norm["record_time"] == "10:19:49"
        assert norm["check_in"] == "10:19:49"
        assert norm["check_out"] == "21:19:57"
        assert norm["latitude"] == 10.807207964
        assert norm["longitude"] == 106.628620666
        assert norm["location"] == "Phường Tân Sơn Nhì, Tân Phú, TP.HCM"

    def test_normalize_attendance_record_null_safe(self):
        # Kiểm tra không crash với null checkInTime, checkOutTime, location, null employeeInfo
        raw_nulls = {
            "employeeInfo": None,
            "recordDate": "2026-09-05",
            "recordTime": None,
            "checkInTime": None,
            "checkOutTime": None,
            "latitude": "invalid_num",
            "longitude": None,
            "locationName": None
        }
        norm = normalize_attendance_record(raw_nulls)
        assert norm["employee_id"] is None
        assert norm["employee_code"] is None
        assert norm["check_in"] is None
        assert norm["check_out"] is None
        assert norm["latitude"] is None
        assert norm["location"] is None

        # Hoàn toàn rỗng hoặc None
        assert normalize_attendance_record(None)["date"] is None

    def test_normalize_attendance_response(self):
        raw_resp = {
            "results": [
                {
                    "employeeInfo": {"id": 1, "codeDisplay": "000001"},
                    "recordDate": "2026-09-01"
                }
            ],
            "total": 1,
            "totalPages": 1
        }
        resp = normalize_attendance_response(raw_resp)
        assert resp["total_records"] == 1
        assert len(resp["records"]) == 1
        assert resp["records"][0]["employee_code"] == "000001"
        assert resp["pagination"]["total"] == 1

        # Rỗng
        empty_resp = normalize_attendance_response(None)
        assert empty_resp["total_records"] == 0
        assert empty_resp["records"] == []

    def test_join_employee_attendance_by_id_success(self):
        """
        JOIN BẮT BUỘC:
        Attendance.employeeInfo.id == Employee.id
        Sau JOIN: employee_code = Employee.codeDisplay
        """
        employees = [
            {
                "id": 16,
                "codeDisplay": "009",
                "firstName": "Vy",
                "lastName": "Lê Hữu Thanh"
            },
            {
                "id": 1,
                "codeDisplay": "000001",
                "firstName": "Tâm",
                "lastName": "Ngô Hoàng"
            }
        ]

        attendances = [
            {
                "employeeInfo": {"id": 16},
                "recordDate": "2026-09-04",
                "checkInTime": "10:19:49"
            },
            {
                "employeeInfo": {"id": 1},
                "recordDate": "2026-09-01",
                "checkInTime": "08:10:00"
            }
        ]

        joined, mapped, unmapped = join_employee_attendance(employees, attendances)
        assert mapped == 2
        assert unmapped == 0
        assert len(joined) == 2

        # Record 1
        assert joined[0]["employee_id"] == 16
        assert joined[0]["employee_code"] == "009"
        assert joined[0]["employee_name"] == "Lê Hữu Thanh Vy"
        assert joined[0]["unmapped"] is False

        # Record 2
        assert joined[1]["employee_id"] == 1
        assert joined[1]["employee_code"] == "000001"
        assert joined[1]["employee_name"] == "Ngô Hoàng Tâm"
        assert joined[1]["unmapped"] is False

    def test_join_employee_attendance_unmapped_does_not_crash(self):
        """
        Trường hợp attendance có employeeInfo.id không tồn tại trong danh sách Employee:
        -> Đánh dấu unmapped = True, không crash.
        """
        employees = [
            {"id": 16, "codeDisplay": "009", "firstName": "Vy", "lastName": "Lê Hữu Thanh"}
        ]
        attendances = [
            {"employeeInfo": {"id": 9999}, "recordDate": "2026-09-05"}
        ]

        joined, mapped, unmapped = join_employee_attendance(employees, attendances)
        assert mapped == 0
        assert unmapped == 1
        assert len(joined) == 1
        assert joined[0]["unmapped"] is True

    def test_join_does_not_use_name_or_fuzzy_match(self):
        """
        Đảm bảo không bao giờ JOIN bằng firstName/lastName nếu ID không khớp.
        """
        employees = [
            {"id": 100, "codeDisplay": "001", "firstName": "Vy", "lastName": "Lê Hữu Thanh"}
        ]
        # Trùng tên nhưng id khác (ví dụ: 16 != 100)
        attendances = [
            {"employeeInfo": {"id": 16, "firstName": "Vy", "lastName": "Lê Hữu Thanh"}, "recordDate": "2026-09-04"}
        ]

        joined, mapped, unmapped = join_employee_attendance(employees, attendances)
        assert mapped == 0
        assert unmapped == 1
        assert joined[0]["unmapped"] is True
