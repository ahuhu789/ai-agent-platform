"""
Module kiểm tra kết nối tới hệ thống My Enterprise Web 1.18.
Kiểm tra khả năng truy cập mạng tới máy chủ nội bộ (yêu cầu VPN TAS).
"""

import socket
import time
from urllib.parse import urlparse
from typing import Dict, Any, Optional

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig

# Biến lưu trữ trạng thái cache kiểm tra kết nối
_CACHE_STATUS: Optional[Dict[str, Any]] = None
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS: float = 10.0  # Cache kết quả trong 10 giây để tránh timeout liên tục


def check_enterprise_web_connection(timeout: float = 2.5, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Kiểm tra xem thiết bị và chatbot có truy cập được Web 1.18 (My Enterprise) hay không.
    Sử dụng socket TCP để kiểm tra tính khả dụng của cổng và máy chủ nội bộ.
    
    Tham số:
    - timeout: Thời gian chờ tối đa (giây). Mặc định 2.5s.
    - force_refresh: Bắt buộc kiểm tra lại ngay, bỏ qua cache.
    
    Trả về dictionary chứa:
    - connected: bool (True nếu truy cập được, False nếu không)
    - url: str (Địa chỉ máy chủ Web 1.18)
    - message: str (Thông báo trạng thái hoặc hướng dẫn kết nối VPN TAS)
    """
    global _CACHE_STATUS, _CACHE_TIMESTAMP

    now = time.time()
    if not force_refresh and _CACHE_STATUS is not None and (now - _CACHE_TIMESTAMP) < _CACHE_TTL_SECONDS:
        return dict(_CACHE_STATUS)

    config = MyEnterpriseConfig.from_env()
    base_url = config.base_url
    parsed = urlparse(base_url)
    host = parsed.hostname or "fm-internal.tasolutions.com.vn"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.close()

        result = {
            "connected": True,
            "host": host,
            "port": port,
            "url": base_url,
            "message": f"Đã kết nối thành công tới máy chủ Web 1.18 ({host}:{port})."
        }
    except Exception as e:
        result = {
            "connected": False,
            "host": host,
            "port": port,
            "url": base_url,
            "error": str(e),
            "message": "Không kết nối được tới server, xin hãy kết nối vpn TAS"
        }

    _CACHE_STATUS = result
    _CACHE_TIMESTAMP = time.time()
    return dict(result)
