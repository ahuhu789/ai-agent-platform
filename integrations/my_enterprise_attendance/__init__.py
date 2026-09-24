"""
Phân hệ tích hợp My Enterprise Attendance & Employee Data Retrieval (Web 1.18).
Cung cấp Client, Config, Mapper, Repository phục vụ trích xuất, chuẩn hóa dữ liệu
và kết nối với Attendance MCP Server.
"""

from integrations.my_enterprise_attendance.config import (
    MyEnterpriseConfig,
    DEFAULT_BASE_URL,
    DEFAULT_EMPLOYEE_PATH,
    DEFAULT_ATTENDANCE_ME_PATH,
    DEFAULT_TIMEOUT_SECONDS
)
from integrations.my_enterprise_attendance.mapper import (
    normalize_employee,
    normalize_attendance_record,
    normalize_attendance_response,
    join_employee_attendance
)
from integrations.my_enterprise_attendance.employee_client import (
    EmployeeClient,
    EmployeeClientError,
    EmployeeClientConfigError,
    EmployeeClientAuthError,
    EmployeeClientApiError,
    EmployeeClientConnectionError,
    EmployeeClientTimeoutError
)
from integrations.my_enterprise_attendance.attendance_client import (
    AttendanceClient,
    AttendanceClientError,
    AttendanceClientConfigError,
    AttendanceClientAuthError,
    AttendanceClientApiError,
    AttendanceClientConnectionError,
    AttendanceClientTimeoutError
)
from integrations.my_enterprise_attendance.client import (
    MyEnterpriseClient,
    MyEnterpriseError,
    MyEnterpriseConfigurationError,
    MyEnterpriseAuthenticationError,
    MyEnterpriseApiError,
    MyEnterpriseConnectionError,
    MyEnterpriseTimeoutError
)
from integrations.my_enterprise_attendance.repository import (
    AttendanceRepository,
    get_repository
)

__all__ = [
    "MyEnterpriseConfig",
    "DEFAULT_BASE_URL",
    "DEFAULT_EMPLOYEE_PATH",
    "DEFAULT_ATTENDANCE_ME_PATH",
    "DEFAULT_TIMEOUT_SECONDS",
    "normalize_employee",
    "normalize_attendance_record",
    "normalize_attendance_response",
    "join_employee_attendance",
    "EmployeeClient",
    "EmployeeClientError",
    "EmployeeClientConfigError",
    "EmployeeClientAuthError",
    "EmployeeClientApiError",
    "EmployeeClientConnectionError",
    "EmployeeClientTimeoutError",
    "AttendanceClient",
    "AttendanceClientError",
    "AttendanceClientConfigError",
    "AttendanceClientAuthError",
    "AttendanceClientApiError",
    "AttendanceClientConnectionError",
    "AttendanceClientTimeoutError",
    "MyEnterpriseClient",
    "MyEnterpriseError",
    "MyEnterpriseConfigurationError",
    "MyEnterpriseAuthenticationError",
    "MyEnterpriseApiError",
    "MyEnterpriseConnectionError",
    "MyEnterpriseTimeoutError",
    "AttendanceRepository",
    "get_repository",
]
