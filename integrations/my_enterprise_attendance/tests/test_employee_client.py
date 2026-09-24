"""
Unit tests cho EmployeeClient (My Enterprise Web 1.18).
Kiểm thử toàn bộ các kịch bản: thành công, rỗng, phân trang metadata, phân trang lặp,
tìm kiếm searchText, lỗi 401, 403, 500, timeout, thiếu token.
Tất cả chạy 100% OFFLINE bằng mocked HTTP.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock
import httpx

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig
from integrations.my_enterprise_attendance.employee_client import (
    EmployeeClient,
    EmployeeClientConfigError,
    EmployeeClientAuthError,
    EmployeeClientApiError,
    EmployeeClientConnectionError,
    EmployeeClientTimeoutError
)


class TestEmployeeClient:
    """Bộ kiểm thử đơn vị cho EmployeeClient."""

    def test_missing_token_raises_config_error(self):
        config = MyEnterpriseConfig(token=None)
        client = EmployeeClient(config)
        with pytest.raises(EmployeeClientConfigError) as exc_info:
            client.get_employees(page=0, size=10)
        assert "MY_ENTERPRISE_TOKEN" in str(exc_info.value)

    def test_invalid_params_raise_value_error(self):
        config = MyEnterpriseConfig(token="valid_token")
        client = EmployeeClient(config)
        with pytest.raises(ValueError) as exc1:
            client.get_employees(page=-1, size=10)
        assert "page" in str(exc1.value)

        with pytest.raises(ValueError) as exc2:
            client.get_employees(page=0, size=0)
        assert "size" in str(exc2.value)

    @patch("httpx.Client.get")
    def test_get_employees_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {
                    "id": 1,
                    "firstName": "Tâm",
                    "lastName": "Ngô Hoàng",
                    "codeDisplay": "000001"
                },
                {
                    "id": 16,
                    "firstName": "Vy",
                    "lastName": "Lê Hữu Thanh",
                    "codeDisplay": "009"
                }
            ],
            "total": 2,
            "totalPages": 1
        }
        mock_get.return_value = mock_resp

        config = MyEnterpriseConfig(token="secret_token")
        client = EmployeeClient(config)
        data = client.get_employees(page=0, size=50, search_text="Vy")

        assert len(data["results"]) == 2
        assert data["results"][0]["codeDisplay"] == "000001"
        assert data["results"][1]["codeDisplay"] == "009"

        # Kiểm tra headers và query params
        call_args = mock_get.call_args
        assert call_args[1]["headers"]["Authorization"] == "Bearer secret_token"
        assert call_args[1]["params"]["searchText"] == "Vy"
        assert call_args[1]["params"]["size"] == 50
        assert call_args[1]["params"]["page"] == 0

    @patch("httpx.Client.get")
    def test_get_employees_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        mock_get.return_value = mock_resp

        config = MyEnterpriseConfig(token="secret_token")
        client = EmployeeClient(config)
        data = client.get_employees(page=0, size=10)
        assert data["results"] == []

    @patch("httpx.Client.get")
    def test_get_all_employees_pagination_with_metadata(self, mock_get):
        # Giả lập 2 trang dựa vào totalPages
        def side_effect(url, params, headers):
            resp = MagicMock()
            resp.status_code = 200
            if params["page"] == 0:
                resp.json.return_value = {
                    "results": [{"id": 1, "codeDisplay": "001"}],
                    "totalPages": 2
                }
            else:
                resp.json.return_value = {
                    "results": [{"id": 2, "codeDisplay": "002"}],
                    "totalPages": 2
                }
            return resp

        mock_get.side_effect = side_effect

        config = MyEnterpriseConfig(token="secret_token")
        client = EmployeeClient(config)
        all_emps = client.get_all_employees(size=1)

        assert len(all_emps) == 2
        assert all_emps[0]["codeDisplay"] == "001"
        assert all_emps[1]["codeDisplay"] == "002"
        assert mock_get.call_count == 2

    @patch("httpx.Client.get")
    def test_get_all_employees_pagination_without_metadata(self, mock_get):
        # Không có totalPages, dừng khi len(results) < size hoặc rỗng
        def side_effect(url, params, headers):
            resp = MagicMock()
            resp.status_code = 200
            if params["page"] == 0:
                resp.json.return_value = {
                    "results": [{"id": 1}, {"id": 2}]  # size=2
                }
            elif params["page"] == 1:
                resp.json.return_value = {
                    "results": [{"id": 3}]  # len < size -> dừng
                }
            else:
                resp.json.return_value = {"results": []}
            return resp

        mock_get.side_effect = side_effect

        config = MyEnterpriseConfig(token="secret_token")
        client = EmployeeClient(config)
        all_emps = client.get_all_employees(size=2)

        assert len(all_emps) == 3
        assert mock_get.call_count == 2

    @patch("httpx.Client.get")
    def test_error_401_unauthorized(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_get.return_value = mock_resp

        client = EmployeeClient(MyEnterpriseConfig(token="expired_token"))
        with pytest.raises(EmployeeClientAuthError) as exc_info:
            client.get_employees()
        assert "401" in str(exc_info.value)

    @patch("httpx.Client.get")
    def test_error_403_forbidden(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_get.return_value = mock_resp

        client = EmployeeClient(MyEnterpriseConfig(token="no_perm_token"))
        with pytest.raises(EmployeeClientAuthError) as exc_info:
            client.get_employees()
        assert "403" in str(exc_info.value)

    @patch("httpx.Client.get")
    def test_error_500_server_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_get.return_value = mock_resp

        client = EmployeeClient(MyEnterpriseConfig(token="valid_token"))
        with pytest.raises(EmployeeClientApiError) as exc_info:
            client.get_employees()
        assert "500" in str(exc_info.value)

    @patch("httpx.Client.get")
    def test_timeout_handling(self, mock_get):
        mock_get.side_effect = httpx.TimeoutException("Timeout")

        client = EmployeeClient(MyEnterpriseConfig(token="valid_token"))
        with pytest.raises(EmployeeClientTimeoutError) as exc_info:
            client.get_employees()
        assert "timeout" in str(exc_info.value).lower()

    @patch("httpx.Client.get")
    def test_connection_error_handling(self, mock_get):
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        client = EmployeeClient(MyEnterpriseConfig(token="valid_token"))
        with pytest.raises(EmployeeClientConnectionError) as exc_info:
            client.get_employees()
        assert "kết nối" in str(exc_info.value).lower()
