"""
Cấu hình tích hợp hệ thống My Enterprise Web 1.18.
Quản lý tập trung các tham số kết nối API thông qua biến môi trường.
Đảm bảo an toàn bảo mật tuyệt đối: không hardcode hoặc in token ra log.
"""

import os
from dataclasses import dataclass
from typing import Optional, Union
from dotenv import load_dotenv

# Nạp các biến môi trường từ tệp .env nếu có
load_dotenv()

DEFAULT_BASE_URL = "https://fm-internal.tasolutions.com.vn:8444"
DEFAULT_EMPLOYEE_PATH = "/api/core/core/api/v1/resources/organization/org-info/employees/suggestion"
DEFAULT_ATTENDANCE_ME_PATH = "/api/core/core/api/v1/resources/employees/attendances/me"
DEFAULT_TIMEOUT_SECONDS = 30.0


def _parse_verify_ssl(value: Optional[str]) -> Union[bool, str]:
    """
    Xử lý cấu hình xác thực chứng chỉ TLS/SSL:
    - Mặc định là True (bảo mật nghiêm ngặt).
    - Hỗ trợ 'false', '0', 'no' để tạm thời bỏ qua kiểm tra chứng chỉ (nếu dùng self-signed).
    - Hỗ trợ đường dẫn tới file CA bundle tùy chỉnh.
    """
    if value is None:
        return True
    val_clean = str(value).strip()
    if val_clean.lower() in ("false", "0", "no", "off"):
        return False
    if val_clean.lower() in ("true", "1", "yes", "on"):
        return True
    if os.path.exists(val_clean):
        return val_clean
    return True


@dataclass
class MyEnterpriseConfig:
    """
    Thông tin cấu hình cho My Enterprise API Client và Repository.
    """
    base_url: str = DEFAULT_BASE_URL
    employee_path: str = DEFAULT_EMPLOYEE_PATH
    attendance_path: str = DEFAULT_ATTENDANCE_ME_PATH
    token: Optional[str] = None
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    verify_ssl: Union[bool, str] = True
    data_source: str = "mock"  # 'mock' hoặc 'real'

    @classmethod
    def from_env(cls) -> "MyEnterpriseConfig":
        """
        Khởi tạo cấu hình tự động từ các biến môi trường.
        """
        raw_base_url = os.getenv("MY_ENTERPRISE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        token = os.getenv("MY_ENTERPRISE_TOKEN")
        if token:
            token = token.strip()
            # Bỏ từ khóa "Bearer " nếu người dùng vô tình copy cả tiền tố
            if token.lower().startswith("bearer "):
                token = token[7:].strip()

        try:
            timeout = float(os.getenv("MY_ENTERPRISE_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
        except (ValueError, TypeError):
            timeout = DEFAULT_TIMEOUT_SECONDS

        verify_ssl = _parse_verify_ssl(os.getenv("MY_ENTERPRISE_VERIFY_SSL"))
        data_source = os.getenv("ATTENDANCE_DATA_SOURCE", "mock").strip().lower()
        if data_source not in ("mock", "real"):
            data_source = "mock"

        return cls(
            base_url=raw_base_url,
            employee_path=DEFAULT_EMPLOYEE_PATH,
            attendance_path=DEFAULT_ATTENDANCE_ME_PATH,
            token=token,
            timeout=timeout,
            verify_ssl=verify_ssl,
            data_source=data_source
        )

    def get_employee_url(self) -> str:
        """URL endpoint danh sách nhân viên gợi ý (suggestion)."""
        endpoint = self.employee_path if self.employee_path.startswith("/") else f"/{self.employee_path}"
        return f"{self.base_url.rstrip('/')}{endpoint}"

    def get_attendance_me_url(self) -> str:
        """URL endpoint chấm công cá nhân (/me)."""
        endpoint = self.attendance_path if self.attendance_path.startswith("/") else f"/{self.attendance_path}"
        return f"{self.base_url.rstrip('/')}{endpoint}"

    def get_full_url(self) -> str:
        """Backward compatibility for existing code referring to get_full_url()."""
        return self.get_attendance_me_url()

    def validate_token(self) -> str:
        """
        Kiểm tra tính sẵn sàng của Token xác thực.
        Ném ngoại lệ ValueError nếu chưa được cung cấp qua môi trường.
        """
        if not self.token:
            raise ValueError(
                "Biến môi trường 'MY_ENTERPRISE_TOKEN' chưa được cấu hình. "
                "Vui lòng thiết lập biến môi trường này hoặc thêm vào tệp .env trước khi gọi API."
            )
        return self.token

    def __repr__(self) -> str:
        """
        Đảm bảo không bao giờ in token bí mật ra màn hình hoặc log.
        """
        masked_token = "***REDACTED***" if self.token else "None"
        return (
            f"MyEnterpriseConfig(base_url='{self.base_url}', "
            f"employee_path='{self.employee_path}', "
            f"attendance_path='{self.attendance_path}', "
            f"token={masked_token}, timeout={self.timeout}, "
            f"verify_ssl={self.verify_ssl}, data_source='{self.data_source}')"
        )
