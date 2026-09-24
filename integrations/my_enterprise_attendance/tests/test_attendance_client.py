"""
Unit tests cho AttendanceClient (My Enterprise Web 1.18).
Kiểm thử các kịch bản: thành công, rỗng, 401, 403, 500, timeout, kiểm tra tham số, phân trang.
Chạy 100% OFFLINE.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import httpx

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig
from integrations.my_enterprise_attendance.attendance_client import (
    AttendanceClient,
    AttendanceClientConfigError,
    AttendanceClientAuthError,
    AttendanceClientApiError,
    AttendanceClientConnectionError,
    AttendanceClientTimeoutError
)


class TestAttendanceClient:
    """Bộ kiểm thử đơn vị cho AttendanceClient."""

    def test_missing_token_raises_config_error(self):
        client = AttendanceClient(MyEnterpriseConfig(token=None))
        with pytest.raises(AttendanceClientConfigError) as exc_info:
            client.get_my_attendance(month_year="2026-09")
        assert "MY_ENTERPRISE_TOKEN" in str(exc_info.value)

    def test_empty_month_year_raises_value_error(self):
        client = AttendanceClient(MyEnterpriseConfig(token="valid_token"))
        with pytest.raises(ValueError) as exc:
            client.get_my_attendance(month_year="")
        assert "month_year" in str(exc.value)

    def test_invalid_page_size_raise_value_error(self):
        client = AttendanceClient(MyEnterpriseConfig(token="valid_token"))
        with pytest.raises(ValueError):
            client.get_my_attendance(month_year="2026-09", page=-1)
        with pytest.raises(ValueError):
            client.get_my_attendance(month_year="2026-09", size=0)

    @patch("httpx.Client.get")
    def test_get_my_attendance_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "employeeInfo": {"id": 16, "codeDisplay": "009"},
                    "recordDate": "2026-09-04",
                    "checkInTime": "10:19:49",
                    "checkOutTime": "21:19:57"
                }
            ],
            "total": 1
        }
        mock_get.return_value = mock_resp

        client = AttendanceClient(MyEnterpriseConfig(token="secret_token"))
        data = client.get_my_attendance(month_year="2026-09-04", page=0, size=50)

        assert len(data["results"]) == 1
        assert data["results"][0]["recordDate"] == "2026-09-04"
        assert mock_get.call_args[1]["headers"]["Authorization"] == "Bearer secret_token"
        assert mock_get.call_args[1]["params"]["monthYear"] == "2026-09-04"

    @patch("httpx.Client.get")
    def test_get_my_attendance_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_get.return_value = mock_resp

        client = AttendanceClient(MyEnterpriseConfig(token="secret_token"))
        data = client.get_my_attendance(month_year="2026-10")
        assert data["results"] == []

    @patch("httpx.Client.get")
    def test_auth_error_401_403(self, mock_get):
        mock_resp_401 = MagicMock()
        mock_resp_401.status_code = 401
        mock_get.return_value = mock_resp_401

        client = AttendanceClient(MyEnterpriseConfig(token="invalid_token"))
        with pytest.raises(AttendanceClientAuthError) as exc_401:
            client.get_my_attendance(month_year="2026-09")
        assert "401" in str(exc_401.value)

        mock_resp_403 = MagicMock()
        mock_resp_403.status_code = 403
        mock_get.return_value = mock_resp_403
        with pytest.raises(AttendanceClientAuthError) as exc_403:
            client.get_my_attendance(month_year="2026-09")
        assert "403" in str(exc_403.value)

    @patch("httpx.Client.get")
    def test_server_error_500(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        client = AttendanceClient(MyEnterpriseConfig(token="token"))
        with pytest.raises(AttendanceClientApiError) as exc:
            client.get_my_attendance(month_year="2026-09")
        assert "500" in str(exc.value)

    @patch("httpx.Client.get")
    def test_timeout_and_connection(self, mock_get):
        mock_get.side_effect = httpx.TimeoutException("Timeout")
        client = AttendanceClient(MyEnterpriseConfig(token="token"))
        with pytest.raises(AttendanceClientTimeoutError):
            client.get_my_attendance(month_year="2026-09")

        mock_get.side_effect = httpx.ConnectError("Connection error")
        with pytest.raises(AttendanceClientConnectionError):
            client.get_my_attendance(month_year="2026-09")

    @patch("httpx.Client.get")
    def test_get_all_my_attendance_pagination(self, mock_get):
        def side_effect(url, params, headers):
            resp = MagicMock()
            resp.status_code = 200
            if params["page"] == 0:
                resp.json.return_value = {"results": [{"id": 1}], "totalPages": 2}
            else:
                resp.json.return_value = {"results": [{"id": 2}], "totalPages": 2}
            return resp

        mock_get.side_effect = side_effect
        client = AttendanceClient(MyEnterpriseConfig(token="token"))
        all_recs = client.get_all_my_attendance(month_year="2026-09", size=1)
        assert len(all_recs) == 2
        assert mock_get.call_count == 2
