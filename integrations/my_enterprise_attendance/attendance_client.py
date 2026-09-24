"""
Attendance API Client cho My Enterprise Web 1.18.

ĐẶC BIỆT LƯU Ý VỀ PHẠM VI (SCOPE CLASSIFICATION):
- Endpoint hiện tại: /api/core/core/api/v1/resources/employees/attendances/me
- Phân loại: TYPE A (Current user attendance API).
- CẢNH BÁO QUAN TRỌNG:
  "THIS ENDPOINT ONLY REPRESENTS CURRENT LOGGED-IN USER ATTENDANCE.
   Attendance all-employee endpoint has not yet been verified from Web 1.18 Network and must not be assumed."
"""

from typing import Dict, Any, List, Optional
import httpx

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig


class AttendanceClientError(Exception):
    """Lớp cơ sở cho lỗi của AttendanceClient."""
    pass


class AttendanceClientConfigError(AttendanceClientError):
    """Lỗi cấu hình (thiếu token)."""
    pass


class AttendanceClientAuthError(AttendanceClientError):
    """Lỗi xác thực HTTP 401 hoặc 403."""
    pass


class AttendanceClientApiError(AttendanceClientError):
    """Lỗi phản hồi HTTP từ server."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class AttendanceClientConnectionError(AttendanceClientError):
    """Lỗi kết nối mạng hoặc VPN."""
    pass


class AttendanceClientTimeoutError(AttendanceClientError):
    """Lỗi timeout khi gọi API."""
    pass


class AttendanceClient:
    """
    Client trích xuất dữ liệu chấm công từ My Enterprise Web 1.18.
    """

    def __init__(self, config: Optional[MyEnterpriseConfig] = None):
        self.config = config or MyEnterpriseConfig.from_env()
        self._http_client: Optional[httpx.Client] = None

    def _get_http_client(self) -> httpx.Client:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.Client(
                timeout=self.config.timeout,
                verify=self.config.verify_ssl
            )
        return self._http_client

    def close(self):
        """Đóng kết nối HTTP Client."""
        if self._http_client is not None and not self._http_client.is_closed:
            self._http_client.close()
            self._http_client = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_my_attendance(
        self,
        month_year: str,
        page: int = 0,
        size: int = 50
    ) -> Dict[str, Any]:
        """
        Truy vấn chấm công cá nhân của tài khoản đăng nhập hiện tại (/me).
        
        LƯU Ý: Endpoint này thuộc TYPE A (Current User).
        Không đại diện cho dữ liệu toàn thể công ty.
        """
        if not month_year or not str(month_year).strip():
            raise ValueError("Tham số 'month_year' không được để trống.")
        if page < 0:
            raise ValueError(f"Tham số 'page' phải >= 0, nhận được: {page}")
        if size <= 0:
            raise ValueError(f"Tham số 'size' phải > 0, nhận được: {size}")

        try:
            token = self.config.validate_token()
        except ValueError as e:
            raise AttendanceClientConfigError(str(e)) from e

        url = self.config.get_attendance_me_url()
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        }
        my_val = str(month_year).strip()
        if len(my_val) == 7 and my_val[4] == "-":
            my_val = f"{my_val}-01"

        params = {
            "page": page,
            "size": size,
            "monthYear": my_val
        }

        client = self._get_http_client()

        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.TimeoutException:
            raise AttendanceClientTimeoutError(
                f"Yêu cầu chấm công bị timeout sau {self.config.timeout}s."
            ) from None
        except httpx.ConnectError:
            raise AttendanceClientConnectionError(
                f"Không thể kết nối tới máy chủ My Enterprise ({self.config.base_url}). Vui lòng kiểm tra VPN nội bộ."
            ) from None
        except httpx.RequestError as e:
            raise AttendanceClientConnectionError(
                f"Lỗi mạng khi gọi Attendance API: {type(e).__name__}"
            ) from None

        status_code = response.status_code
        if status_code == 200:
            try:
                data = response.json()
                if not isinstance(data, dict):
                    return {"results": []}
                return data
            except Exception as e:
                raise AttendanceClientApiError(
                    f"Không thể phân tích dữ liệu JSON từ Attendance API: {e}",
                    status_code=status_code,
                    response_text=response.text[:500]
                ) from None
        elif status_code == 401:
            raise AttendanceClientAuthError(
                "Xác thực thất bại (HTTP 401 Unauthorized). Token không hợp lệ hoặc đã hết hạn."
            )
        elif status_code == 403:
            raise AttendanceClientAuthError(
                "Truy cập bị từ chối (HTTP 403 Forbidden). Tài khoản không có quyền truy cập dữ liệu chấm công."
            )
        elif status_code == 404:
            raise AttendanceClientApiError(
                f"Không tìm thấy endpoint (HTTP 404 Not Found): {self.config.attendance_path}",
                status_code=status_code,
                response_text=response.text[:500]
            )
        else:
            raise AttendanceClientApiError(
                f"Attendance API trả về mã lỗi HTTP {status_code}.",
                status_code=status_code,
                response_text=response.text[:500]
            )

    def get_all_my_attendance(
        self,
        month_year: str,
        size: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Lấy toàn bộ bản ghi chấm công cá nhân trong tháng/ngày chỉ định.
        Tự động duyệt qua các trang phân trang.
        """
        all_records: List[Dict[str, Any]] = []
        page = 0
        max_pages = 100

        while page < max_pages:
            data = self.get_my_attendance(month_year=month_year, page=page, size=size)
            results = data.get("results")
            if not isinstance(results, list) or len(results) == 0:
                break

            all_records.extend(results)

            total_pages = data.get("totalPages")
            if total_pages is not None:
                try:
                    if page + 1 >= int(total_pages):
                        break
                except (ValueError, TypeError):
                    pass

            has_next = data.get("hasNext")
            if has_next is not None and has_next is False:
                break

            if len(results) < size:
                break

            page += 1

        return all_records

    def filter_attendances(
        self,
        page: int = 0,
        size: int = 100,
        filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Truy vấn chấm công của toàn bộ nhân viên công ty qua endpoint /filter.
        """
        try:
            token = self.config.validate_token()
        except ValueError as e:
            raise AttendanceClientConfigError(str(e)) from e

        url = f"{self.config.base_url.rstrip('/')}/api/core/core/api/v1/resources/employees/attendances/filter"
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        params = {"page": page, "size": size}
        body = {"filters": filters or {}}

        client = self._get_http_client()
        try:
            response = client.post(url, params=params, headers=headers, json=body)
        except httpx.TimeoutException:
            raise AttendanceClientTimeoutError(f"Yêu cầu chấm công bị timeout sau {self.config.timeout}s.") from None
        except httpx.ConnectError:
            raise AttendanceClientConnectionError(f"Không thể kết nối tới máy chủ My Enterprise ({self.config.base_url}).") from None
        except httpx.RequestError as e:
            raise AttendanceClientConnectionError(f"Lỗi mạng khi gọi Attendance Filter API: {type(e).__name__}") from None

        status_code = response.status_code
        if status_code == 200:
            try:
                data = response.json()
                if not isinstance(data, dict):
                    return {"results": []}
                return data
            except Exception as e:
                raise AttendanceClientApiError(f"Không thể parse JSON: {e}", status_code=status_code)
        elif status_code == 401:
            raise AttendanceClientAuthError("Xác thực thất bại (HTTP 401).")
        elif status_code == 403:
            raise AttendanceClientAuthError("Truy cập bị từ chối (HTTP 403).")
        else:
            raise AttendanceClientApiError(f"Attendance Filter API lỗi HTTP {status_code}.", status_code=status_code, response_text=response.text[:500])

    def get_all_company_attendance(self, size: int = 100) -> List[Dict[str, Any]]:
        """
        Lấy toàn bộ bản ghi chấm công của tất cả nhân viên công ty.
        """
        all_records: List[Dict[str, Any]] = []
        page = 0
        while page < 100:
            data = self.filter_attendances(page=page, size=size, filters={})
            results = data.get("results")
            if not isinstance(results, list) or len(results) == 0:
                break
            all_records.extend(results)
            if len(results) < size:
                break
            page += 1
        return all_records

