"""
Unit tests cho crawler My Enterprise Web 1.18 (crawl_employees.py).
Kiểm thử toàn bộ các yêu cầu:
1. Missing token -> dừng tại bước crawl, không tạo dữ liệu giả (Yêu cầu 13).
2. Lỗi mạng/VPN/Auth (401, 403, timeout, connection error) -> dừng, báo chính xác lỗi.
3. Pagination đầy đủ nhiều trang (Yêu cầu 3).
4. Mapping chính xác field: employee_id=id, first_name=firstName, last_name=lastName, employee_code=codeDisplay (Yêu cầu 4).
5. Nghiêm cấm dùng id làm mã nhân viên, nghiêm cấm tự sinh mã (Yêu cầu 4).
6. Lưu raw response nguyên bản vào data/raw/employees_raw.json (Yêu cầu 7).
7. Lưu normalized data vào data/mock/employees.json (Yêu cầu 8).
8. Phát hiện duplicate employee_id và employee_code (Yêu cầu 9).
9. Kiểm tra JOIN attendance bằng employee_id -> employee_code (Yêu cầu 11).
10. Định dạng báo cáo đầy đủ EMPLOYEE CRAWL RESULT và DATA VALIDATION (Yêu cầu 12).
"""

import os
import sys
import json
import pytest
from unittest.mock import patch, MagicMock
import httpx

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from integrations.my_enterprise_attendance.crawl_employees import crawl_employees


class TestEmployeeCrawler:
    """Bộ test kiểm thử module crawl nhân viên."""

    def test_missing_token_stops_immediately(self, monkeypatch):
        """Yêu cầu 13: Khi thiếu token, DỪNG ngay lập tức, không tạo dữ liệu giả."""
        monkeypatch.delenv("MY_ENTERPRISE_TOKEN", raising=False)
        result = crawl_employees()
        assert result["success"] is False
        assert result["error_type"] == "MISSING_TOKEN"

    def test_unauthorized_401_stops_immediately(self, monkeypatch):
        """Yêu cầu 13: Khi API trả về 401 Unauthorized, DỪNG ngay lập tức."""
        monkeypatch.setenv("MY_ENTERPRISE_TOKEN", "mock_expired_token")

        mock_resp = MagicMock()
        mock_resp.status_code = 401

        with patch("httpx.Client.get", return_value=mock_resp):
            result = crawl_employees()
            assert result["success"] is False
            assert result["error_type"] == "AUTH_401_UNAUTHORIZED"

    def test_connection_error_stops_immediately(self, monkeypatch):
        """Yêu cầu 13: Khi lỗi mạng/VPN không kết nối được server, DỪNG ngay lập tức."""
        monkeypatch.setenv("MY_ENTERPRISE_TOKEN", "mock_valid_token")

        with patch("httpx.Client.get", side_effect=httpx.ConnectError("Connection refused")):
            result = crawl_employees()
            assert result["success"] is False
            assert result["error_type"] == "CONNECTION_ERROR"

    def test_pagination_and_field_mapping(self, monkeypatch, tmp_path):
        """
        Yêu cầu 3 & 4 & 7 & 8 & 9 & 11 & 12:
        - Crawl đầy đủ qua các trang phân trang (page 0 -> page 1).
        - Mapping đúng các trường: employee_id = id, employee_code = codeDisplay.
        - Lưu raw file và mock file.
        - Kiểm tra trùng lặp và JOIN.
        """
        monkeypatch.setenv("MY_ENTERPRISE_TOKEN", "mock_valid_token")

        raw_path = str(tmp_path / "employees_raw.json")
        mock_path = str(tmp_path / "employees.json")
        fixture_path = str(tmp_path / "employees_mock.json")
        att_fixture_path = str(tmp_path / "attendance_mock.json")

        # Chuẩn bị dữ liệu attendance mẫu để test JOIN theo ID (attendance.employeeInfo.id == employee.employee_id)
        att_data = [
            {
                "employeeInfo": {
                    "id": 16,
                    "codeDisplay": "009",
                    "firstName": "Vy",
                    "lastName": "Lê Hữu Thanh"
                },
                "recordDate": "2026-09-04",
                "checkInTime": "08:15:00"
            }
        ]
        with open(att_fixture_path, "w", encoding="utf-8") as f:
            json.dump(att_data, f)

        # Mock 2 trang dữ liệu API
        page_0_data = {
            "results": [
                {"id": 16, "firstName": "Vy", "lastName": "Lê Hữu Thanh", "codeDisplay": "009"},
                {"id": 1, "firstName": "Tâm", "lastName": "Ngô Hoàng", "codeDisplay": "000001"}
            ],
            "totalPages": 2,
            "hasNext": True
        }
        page_1_data = {
            "results": [
                {"id": 105, "firstName": "Hải", "lastName": "Hoàng Nam", "codeDisplay": "000012"}
            ],
            "totalPages": 2,
            "hasNext": False
        }

        mock_resp_0 = MagicMock()
        mock_resp_0.status_code = 200
        mock_resp_0.json.return_value = page_0_data

        mock_resp_1 = MagicMock()
        mock_resp_1.status_code = 200
        mock_resp_1.json.return_value = page_1_data

        def mock_get(*args, **kwargs):
            page = kwargs.get("params", {}).get("page", 0)
            if page == 0:
                return mock_resp_0
            return mock_resp_1

        with patch("httpx.Client.get", side_effect=mock_get), \
             patch("integrations.my_enterprise_attendance.crawl_employees.RAW_DATA_PATH", raw_path), \
             patch("integrations.my_enterprise_attendance.crawl_employees.MOCK_DATA_PATH", mock_path), \
             patch("integrations.my_enterprise_attendance.crawl_employees.FIXTURE_DATA_PATH", fixture_path), \
             patch("integrations.my_enterprise_attendance.crawl_employees.FIXTURE_ATTENDANCE_PATH", att_fixture_path):

            result = crawl_employees()

            # 1. Kiểm tra thành công và phân trang
            assert result["success"] is True
            assert result["total_pages"] == 2
            assert result["total_employees"] == 3
            assert result["valid_employees"] == 3
            assert len(result["duplicate_ids"]) == 0
            assert len(result["duplicate_codes"]) == 0

            # 2. Kiểm tra lưu Raw response (giữ nguyên API response, không normalize)
            assert os.path.exists(raw_path)
            with open(raw_path, "r", encoding="utf-8") as f:
                saved_raw = json.load(f)
            assert len(saved_raw) == 3
            assert saved_raw[0]["id"] == 16
            assert saved_raw[0]["codeDisplay"] == "009"

            # 3. Kiểm tra lưu Normalized dataset
            assert os.path.exists(mock_path)
            with open(mock_path, "r", encoding="utf-8") as f:
                saved_mock = json.load(f)
            assert len(saved_mock) == 3

            emp_0 = saved_mock[0]
            # Yêu cầu 4: mapping field
            assert emp_0["employee_id"] == 16
            assert emp_0["employee_code"] == "009"
            assert emp_0["first_name"] == "Vy"
            assert emp_0["last_name"] == "Lê Hữu Thanh"
            assert emp_0["name"] == "Lê Hữu Thanh Vy"

            # Đảm bảo employee_code không bị nhầm thành id
            assert emp_0["employee_code"] != emp_0["employee_id"]

            # 4. Kiểm tra báo cáo
            assert "EMPLOYEE CRAWL RESULT" in result["report"]
            assert "DATA VALIDATION" in result["report"]
            assert "employee_id mapping: PASS" in result["report"]
            assert "employee_code = codeDisplay: PASS" in result["report"]
            assert "attendance employee JOIN: PASS" in result["report"]

    def test_duplicate_detection(self, monkeypatch, tmp_path):
        """Yêu cầu 9: Kiểm tra và phát hiện duplicate employee_id và employee_code."""
        monkeypatch.setenv("MY_ENTERPRISE_TOKEN", "mock_valid_token")

        raw_path = str(tmp_path / "employees_raw.json")
        mock_path = str(tmp_path / "employees.json")
        fixture_path = str(tmp_path / "employees_mock.json")
        att_fixture_path = str(tmp_path / "attendance_mock.json")

        page_data = {
            "results": [
                {"id": 10, "firstName": "An", "lastName": "Nguyen", "codeDisplay": "CODE_A"},
                {"id": 10, "firstName": "Binh", "lastName": "Tran", "codeDisplay": "CODE_B"}, # Duplicate ID 10
                {"id": 11, "firstName": "Cuong", "lastName": "Le", "codeDisplay": "CODE_A"},  # Duplicate CODE_A
            ],
            "totalPages": 1,
            "hasNext": False
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = page_data

        with patch("httpx.Client.get", return_value=mock_resp), \
             patch("integrations.my_enterprise_attendance.crawl_employees.RAW_DATA_PATH", raw_path), \
             patch("integrations.my_enterprise_attendance.crawl_employees.MOCK_DATA_PATH", mock_path), \
             patch("integrations.my_enterprise_attendance.crawl_employees.FIXTURE_DATA_PATH", fixture_path), \
             patch("integrations.my_enterprise_attendance.crawl_employees.FIXTURE_ATTENDANCE_PATH", att_fixture_path):

            result = crawl_employees()
            assert result["success"] is True
            assert 10 in result["duplicate_ids"]
            assert "CODE_A" in result["duplicate_codes"]
            assert "duplicate employee_id: 1 ([10])" in result["report"]
            assert "duplicate employee_code: 1 (['CODE_A'])" in result["report"]
