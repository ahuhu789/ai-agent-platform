"""
Employee API Client cho My Enterprise Web 1.18.
Trích xuất danh sách nhân viên từ API /resources/organization/org-info/employees/suggestion.
Hỗ trợ phân trang tự động, tìm kiếm theo tên/mã và xử lý lỗi mạng an toàn.
"""

from typing import Dict, Any, List, Optional
import httpx

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig


class EmployeeClientError(Exception):
    """Lớp cơ sở cho lỗi của EmployeeClient."""
    pass


class EmployeeClientConfigError(EmployeeClientError):
    """Lỗi cấu hình (thiếu token hoặc URL)."""
    pass


class EmployeeClientAuthError(EmployeeClientError):
    """Lỗi xác thực HTTP 401 hoặc 403."""
    pass


class EmployeeClientApiError(EmployeeClientError):
    """Lỗi phản hồi HTTP từ server."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_text: Optional[str] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class EmployeeClientConnectionError(EmployeeClientError):
    """Lỗi kết nối mạng hoặc VPN."""
    pass


class EmployeeClientTimeoutError(EmployeeClientError):
    """Lỗi quá thời gian chờ (Timeout)."""
    pass


class EmployeeClient:
    """
    Client kết nối và trích xuất danh sách nhân viên từ My Enterprise Web 1.18.
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

    def get_employees(
        self,
        page: int = 0,
        size: int = 100,
        search_text: str = ""
    ) -> Dict[str, Any]:
        """
        Gửi yêu cầu GET tới API danh sách nhân viên (suggestion).
        
        Endpoint:
            GET /api/core/core/api/v1/resources/organization/org-info/employees/suggestion
            
        Tham số:
            page: Thứ tự trang (bắt đầu từ 0)
            size: Kích thước trang (mặc định 100)
            search_text: Từ khóa tìm kiếm (tên, mã nhân viên...)
            
        Trả về:
            dict: Phản hồi JSON chứa 'results' danh sách nhân viên và metadata nếu có.
        """
        if page < 0:
            raise ValueError(f"Tham số 'page' phải >= 0, nhận được: {page}")
        if size <= 0:
            raise ValueError(f"Tham số 'size' phải > 0, nhận được: {size}")

        try:
            token = self.config.validate_token()
        except ValueError as e:
            raise EmployeeClientConfigError(str(e)) from e

        url = self.config.get_employee_url()
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}"
        }
        params = {
            "size": size,
            "page": page,
            "searchText": search_text or ""
        }

        client = self._get_http_client()

        try:
            response = client.get(url, params=params, headers=headers)
        except httpx.TimeoutException:
            raise EmployeeClientTimeoutError(
                f"Yêu cầu lấy danh sách nhân viên bị timeout sau {self.config.timeout}s."
            ) from None
        except httpx.ConnectError:
            raise EmployeeClientConnectionError(
                f"Không thể kết nối tới máy chủ My Enterprise ({self.config.base_url}). Vui lòng kiểm tra VPN nội bộ."
            ) from None
        except httpx.RequestError as e:
            raise EmployeeClientConnectionError(
                f"Lỗi mạng khi gọi Employee API: {type(e).__name__}"
            ) from None

        status_code = response.status_code
        if status_code == 200:
            try:
                data = response.json()
                if not isinstance(data, dict):
                    return {"results": []}
                return data
            except Exception as e:
                raise EmployeeClientApiError(
                    f"Không thể phân tích dữ liệu JSON từ Employee API: {e}",
                    status_code=status_code,
                    response_text=response.text[:500]
                ) from None
        elif status_code == 401:
            raise EmployeeClientAuthError(
                "Xác thực thất bại (HTTP 401 Unauthorized). Token không hợp lệ hoặc đã hết hạn."
            )
        elif status_code == 403:
            raise EmployeeClientAuthError(
                "Truy cập bị từ chối (HTTP 403 Forbidden). Tài khoản không có quyền xem danh sách nhân viên."
            )
        elif status_code == 404:
            raise EmployeeClientApiError(
                f"Không tìm thấy endpoint (HTTP 404 Not Found): {self.config.employee_path}",
                status_code=status_code,
                response_text=response.text[:500]
            )
        else:
            raise EmployeeClientApiError(
                f"Employee API trả về mã lỗi HTTP {status_code}.",
                status_code=status_code,
                response_text=response.text[:500]
            )

    def get_all_employees(
        self,
        size: int = 100,
        search_text: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Lấy toàn bộ danh sách nhân viên mà API cho phép truy cập.
        Tự động phân trang an toàn:
        - Sử dụng metadata (totalPages, totalElements, hasNext) nếu API cung cấp.
        - Nếu không có metadata, lặp tuần tự page=0, 1, 2... cho tới khi results rỗng hoặc < size.
        """
        all_employees: List[Dict[str, Any]] = []
        page = 0
        max_pages = 500  # Giới hạn an toàn chống vòng lặp vô tận

        while page < max_pages:
            data = self.get_employees(page=page, size=size, search_text=search_text)
            results = data.get("results")
            if not isinstance(results, list) or len(results) == 0:
                break

            all_employees.extend(results)

            # 1. Kiểm tra nếu có metadata phân trang từ response
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

            # 2. Nếu số kết quả trả về nhỏ hơn kích thước trang yêu cầu -> đã tới trang cuối
            if len(results) < size:
                break

            page += 1

        return all_employees
