"""
Unit tests cho phân hệ My Enterprise Attendance.
Sử dụng mocked HTTP calls để kiểm thử toàn diện mà không phụ thuộc vào mạng nội bộ hay token thật.
"""

import os
import sys
from pathlib import Path

# Đảm bảo root của project luôn có trong sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from unittest.mock import patch, MagicMock
import httpx

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig, _parse_verify_ssl
from integrations.my_enterprise_attendance.mapper import (
    normalize_attendance_record,
    normalize_attendance_response,
    _extract_full_name
)
from integrations.my_enterprise_attendance.client import (
    MyEnterpriseClient,
    MyEnterpriseConfigurationError,
    MyEnterpriseAuthenticationError,
    MyEnterpriseApiError,
    MyEnterpriseConnectionError,
    MyEnterpriseTimeoutError
)


# Sample mock response observed from Web 1.18 DevTools
MOCK_VALID_RESPONSE = {
    "results": [
        {
            "id": None,
            "employeeInfo": {
                "id": 16,
                "firstName": "Vy",
                "lastName": "Lê Hữu Thanh",
                "code": 16,
                "codeDisplay": "009",
                "primaryEmail": "vy.le@tasolutions.com.vn",
                "orgId": 2,
                "orgName": "Bộ Phận Thực Tập"
            },
            "extEmployeeId": None,
            "recordDate": "2026-09-04",
            "recordTime": "10:19:49",
            "checkInTime": "10:19:49",
            "checkOutTime": "21:19:57",
            "latitude": 10.807207964,
            "longitude": 106.628620666,
            "locationName": "Phường Tân Sơn Nhì, Tân Phú, TP.HCM"
        }
    ],
    "total": 1,
    "page": 0,
    "size": 50
}


# =====================================================================
# 1. Cấu hình & Bảo Mật (Config & Security Tests)
# =====================================================================

def test_config_token_redaction():
    """Kiểm tra token không bao giờ bị lộ trong __repr__ của Config."""
    cfg = MyEnterpriseConfig(token="super_secret_token_12345")
    repr_str = repr(cfg)
    assert "super_secret_token_12345" not in repr_str
    assert "***REDACTED***" in repr_str


def test_missing_token_raises_configuration_error():
    """Gọi client khi chưa có token phải ném lỗi MyEnterpriseConfigurationError rõ ràng."""
    cfg = MyEnterpriseConfig(token=None)
    client = MyEnterpriseClient(config=cfg)
    with pytest.raises(MyEnterpriseConfigurationError) as exc_info:
        client.get_my_attendance(month_year="2026-09-06")
    assert "MY_ENTERPRISE_TOKEN" in str(exc_info.value)


def test_parse_verify_ssl():
    """Kiểm tra phân tích cờ cấu hình TLS/SSL."""
    assert _parse_verify_ssl("true") is True
    assert _parse_verify_ssl("1") is True
    assert _parse_verify_ssl("false") is False
    assert _parse_verify_ssl("0") is False
    assert _parse_verify_ssl(None) is True


# =====================================================================
# 2. Mapper Tests (Xử lý an toàn dữ liệu)
# =====================================================================

def test_mapper_successful_normalization():
    """Chuẩn hóa chính xác bản ghi đầy đủ trường."""
    record = MOCK_VALID_RESPONSE["results"][0]
    normalized = normalize_attendance_record(record)
    
    assert normalized["employee_id"] == 16
    assert normalized["employee_code"] == "009"
    assert normalized["employee_name"] == "Lê Hữu Thanh Vy"
    assert normalized["date"] == "2026-09-04"
    assert normalized["record_time"] == "10:19:49"
    assert normalized["check_in"] == "10:19:49"
    assert normalized["check_out"] == "21:19:57"
    assert normalized["latitude"] == 10.807207964
    assert normalized["longitude"] == 106.628620666
    assert "Tân Sơn Nhì" in normalized["location"]


def test_mapper_empty_results():
    """Xử lý an toàn khi results là mảng rỗng."""
    raw = {"results": []}
    response = normalize_attendance_response(raw)
    assert response["records"] == []
    assert response["total_records"] == 0


def test_mapper_missing_employee_info():
    """Không bị crash khi employeeInfo là None hoặc dictionary rỗng."""
    record = {
        "employeeInfo": None,
        "recordDate": "2026-09-04",
        "recordTime": "08:30:00",
        "checkInTime": "08:30:00",
        "checkOutTime": "17:30:00"
    }
    normalized = normalize_attendance_record(record)
    assert normalized["employee_id"] is None
    assert normalized["employee_code"] is None
    assert normalized["employee_name"] is None
    assert normalized["date"] == "2026-09-04"


def test_mapper_null_checkin_checkout():
    """Xử lý an toàn khi nhân viên nghỉ hoặc chưa check-in/out (giá trị null)."""
    record = {
        "employeeInfo": {"id": 20, "code": "020", "firstName": "An", "lastName": "Trần"},
        "recordDate": "2026-09-05",
        "recordTime": None,
        "checkInTime": None,
        "checkOutTime": None,
        "locationName": None,
        "latitude": None,
        "longitude": None
    }
    normalized = normalize_attendance_record(record)
    assert normalized["employee_id"] == 20
    assert normalized["employee_code"] == "020"
    assert normalized["employee_name"] == "Trần An"
    assert normalized["check_in"] is None
    assert normalized["check_out"] is None
    assert normalized["location"] is None


def test_mapper_preserves_pagination_info():
    """Bảo toàn các siêu dữ liệu phân trang trong response."""
    raw = {
        "results": [],
        "total": 120,
        "totalPages": 3,
        "page": 0,
        "size": 50
    }
    response = normalize_attendance_response(raw)
    assert response["pagination"]["total"] == 120
    assert response["pagination"]["totalPages"] == 3
    assert response["pagination"]["page"] == 0
    assert response["pagination"]["size"] == 50


# =====================================================================
# 3. Client HTTP & Request Validation Tests (Mocked)
# =====================================================================

@patch("httpx.Client.get")
def test_client_query_params_and_headers(mock_get):
    """Kiểm tra query parameters và headers gửi đi chính xác."""
    # Giả lập response 200
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_VALID_RESPONSE
    mock_get.return_value = mock_resp

    test_token = "dummy_test_token_xyz"
    cfg = MyEnterpriseConfig(
        base_url="https://fm-internal.tasolutions.com.vn:8444",
        token=test_token
    )
    client = MyEnterpriseClient(config=cfg)
    
    result = client.get_my_attendance(month_year="2026-09-06", page=1, size=25)

    assert result == MOCK_VALID_RESPONSE
    mock_get.assert_called_once()
    call_args, call_kwargs = mock_get.call_args
    
    # Kiểm tra URL
    assert call_args[0] == "https://fm-internal.tasolutions.com.vn:8444/api/core/core/api/v1/resources/employees/attendances/me"
    
    # Kiểm tra params
    params = call_kwargs["params"]
    assert params["monthYear"] == "2026-09-06"
    assert params["page"] == 1
    assert params["size"] == 25
    
    # Kiểm tra headers
    headers = call_kwargs["headers"]
    assert headers["Accept"] == "application/json"
    assert headers["Authorization"] == f"Bearer {test_token}"


@patch("httpx.Client.get")
def test_client_normalized_wrapper(mock_get):
    """Kiểm tra phương thức tiện ích get_my_normalized_attendance."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = MOCK_VALID_RESPONSE
    mock_get.return_value = mock_resp

    cfg = MyEnterpriseConfig(token="token_123")
    client = MyEnterpriseClient(config=cfg)

    data = client.get_my_normalized_attendance(month_year="2026-09-06")
    assert "records" in data
    assert len(data["records"]) == 1
    assert data["records"][0]["employee_name"] == "Lê Hữu Thanh Vy"
    assert data["total_records"] == 1


@patch("httpx.Client.get")
def test_client_http_401_unauthorized(mock_get):
    """Kiểm tra xử lý lỗi 401 Unauthorized."""
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_get.return_value = mock_resp

    cfg = MyEnterpriseConfig(token="expired_token")
    client = MyEnterpriseClient(config=cfg)

    with pytest.raises(MyEnterpriseAuthenticationError) as exc_info:
        client.get_my_attendance(month_year="2026-09-06")
    assert "401" in str(exc_info.value)
    # Tuyệt đối không chứa token trong thông điệp lỗi
    assert "expired_token" not in str(exc_info.value)


@patch("httpx.Client.get")
def test_client_http_403_forbidden(mock_get):
    """Kiểm tra xử lý lỗi 403 Forbidden."""
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_get.return_value = mock_resp

    cfg = MyEnterpriseConfig(token="no_permission_token")
    client = MyEnterpriseClient(config=cfg)

    with pytest.raises(MyEnterpriseAuthenticationError) as exc_info:
        client.get_my_attendance(month_year="2026-09-06")
    assert "403" in str(exc_info.value)


@patch("httpx.Client.get")
def test_client_http_500_server_error(mock_get):
    """Kiểm tra xử lý lỗi 500 từ server."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    mock_get.return_value = mock_resp

    cfg = MyEnterpriseConfig(token="valid_token")
    client = MyEnterpriseClient(config=cfg)

    with pytest.raises(MyEnterpriseApiError) as exc_info:
        client.get_my_attendance(month_year="2026-09-06")
    assert exc_info.value.status_code == 500


@patch("httpx.Client.get")
def test_client_timeout_error(mock_get):
    """Kiểm tra xử lý khi bị timeout mạng."""
    mock_get.side_effect = httpx.TimeoutException("Read timed out")

    cfg = MyEnterpriseConfig(token="valid_token", timeout=10.0)
    client = MyEnterpriseClient(config=cfg)

    with pytest.raises(MyEnterpriseTimeoutError) as exc_info:
        client.get_my_attendance(month_year="2026-09-06")
    assert "timeout" in str(exc_info.value).lower()


@patch("httpx.Client.get")
def test_client_connect_error(mock_get):
    """Kiểm tra xử lý khi không kết nối được tới host."""
    mock_get.side_effect = httpx.ConnectError("Failed to connect")

    cfg = MyEnterpriseConfig(token="valid_token")
    client = MyEnterpriseClient(config=cfg)

    with pytest.raises(MyEnterpriseConnectionError) as exc_info:
        client.get_my_attendance(month_year="2026-09-06")
    assert "kết nối" in str(exc_info.value).lower()


def test_client_input_validation():
    """Kiểm tra validation các tham số đầu vào (month_year rỗng, page âm, size <= 0)."""
    cfg = MyEnterpriseConfig(token="valid_token")
    client = MyEnterpriseClient(config=cfg)

    with pytest.raises(ValueError):
        client.get_my_attendance(month_year="")

    with pytest.raises(ValueError):
        client.get_my_attendance(month_year="2026-09-06", page=-1)

    with pytest.raises(ValueError):
        client.get_my_attendance(month_year="2026-09-06", size=0)
