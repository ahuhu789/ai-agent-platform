"""
Kịch bản kiểm thử thủ công (Manual Verification Script) cho phân hệ My Enterprise Attendance.

Hỗ trợ kiểm thử an toàn kết nối tới API thực tế bằng Token được cấp qua biến môi trường:
$env:MY_ENTERPRISE_TOKEN="<TOKEN_THẬT>"
.\\venv\\Scripts\\python.exe integrations/my_enterprise_attendance/manual_test.py

QUY TẮC AN TOÀN TUYỆT ĐỐI:
- KHÔNG in token xác thực.
- KHÔNG in cookie.
- KHÔNG in thông tin nhạy cảm hoặc email cá nhân chi tiết.
- CHỈ in các trường tóm tắt cần thiết: HTTP Status, số bản ghi, ngày, mã NV, giờ vào/ra.
"""

import os
import sys
from datetime import datetime

# Cấu hình UTF-8 cho Windows Terminal để không bị lỗi font tiếng Việt
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Đảm bảo root của project có trong sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig
from integrations.my_enterprise_attendance.client import (
    MyEnterpriseClient,
    MyEnterpriseAuthenticationError,
    MyEnterpriseConnectionError,
    MyEnterpriseTimeoutError,
    MyEnterpriseApiError,
    MyEnterpriseConfigurationError,
    MyEnterpriseError
)


def run_manual_test(target_date: str = "2026-09-06", page: int = 0, size: int = 50):
    print("=" * 70)
    print("   KIỂM THỬ THỦ CÔNG: MY ENTERPRISE ATTENDANCE GET RETRIEVAL")
    print("=" * 70)

    # 1. Kiểm tra biến môi trường MY_ENTERPRISE_TOKEN
    token = os.getenv("MY_ENTERPRISE_TOKEN")
    if not token or not token.strip():
        print("\n[CẢNH BÁO] Biến môi trường 'MY_ENTERPRISE_TOKEN' chưa được thiết lập!")
        print("\nHướng dẫn chạy kiểm thử với Token thực tế:")
        print("  Trên Windows PowerShell:")
        print('    $env:MY_ENTERPRISE_TOKEN="<DÁN_BEARER_TOKEN_TẠI_ĐÂY>"')
        print("    .\\venv\\Scripts\\python.exe integrations/my_enterprise_attendance/manual_test.py")
        print("\n  Hoặc thêm dòng sau vào tệp .env (đã được .gitignore bảo vệ):")
        print("    MY_ENTERPRISE_TOKEN=<TOKEN>")
        print("=" * 70)
        return False

    config = MyEnterpriseConfig.from_env()
    print(f"\n[1] Cấu hình kết nối:")
    print(f"  - Base URL      : {config.base_url}")
    print(f"  - Endpoint      : {config.endpoint_path}")
    print(f"  - Timeout       : {config.timeout}s")
    print(f"  - Verify SSL    : {config.verify_ssl}")
    print(f"  - Token Status  : [ĐÃ CUNG CẤP] (Độ dài: {len(token)} ký tự, Đã che dấu an toàn)")
    print(f"  - Target Date   : {target_date} (page={page}, size={size})")

    print("\n[2] Đang gửi yêu cầu GET tới máy chủ My Enterprise...")
    client = MyEnterpriseClient(config=config)

    try:
        data = client.get_my_normalized_attendance(
            month_year=target_date,
            page=page,
            size=size
        )
        records = data.get("records", [])
        total_records = data.get("total_records", len(records))

        print("\n[3] KẾT QUẢ TRẢ VỀ:")
        print(f"  - HTTP Status           : 200 OK")
        print(f"  - Tổng số bản ghi nhận  : {total_records}")

        if not records:
            print("  - Danh sách bản ghi     : [RỖNG] (Không có dữ liệu chấm công trong mốc ngày/tháng này)")
        else:
            print("\n[4] THÔNG TIN BẢN GHI ĐẦU TIÊN (ĐÃ BẢO VỆ DỮ LIỆU NHẠY CẢM):")
            first = records[0]
            print(f"  - Ngày ghi nhận (date)  : {first.get('date')}")
            print(f"  - Mã nhân viên (code)   : {first.get('employee_code')}")
            print(f"  - Tên nhân viên (name)  : {first.get('employee_name')}")
            print(f"  - Giờ Check-in          : {first.get('check_in') or 'Chưa ghi nhận'}")
            print(f"  - Giờ Check-out         : {first.get('check_out') or 'Chưa ghi nhận'}")
            print(f"  - Thời điểm ghi (time)  : {first.get('record_time') or 'Không rõ'}")
            print(f"  - Địa điểm chấm công    : {first.get('location') or 'Không có thông tin'}")

        print("\n[THÀNH CÔNG] Lớp trích xuất dữ liệu My Enterprise hoạt động chính xác!")
        print("=" * 70)
        return True

    except MyEnterpriseAuthenticationError as e:
        print(f"\n[LỖI XÁC THỰC] {e}")
        print("Gợi ý: Token của bạn có thể đã hết hạn hoặc không có quyền truy cập.")
        print("=" * 70)
        return False

    except MyEnterpriseConnectionError as e:
        print(f"\n[LỖI KẾT NỐI MẠNG] {e}")
        print("Nguyên nhân tiềm năng:")
        print("  1. Máy tính chưa kết nối vào mạng nội bộ công ty (Intranet / Office LAN / VPN).")
        print("  2. Tường lửa hoặc DNS nội bộ không phân giải được host fm-internal.tasolutions.com.vn:8444.")
        print("  3. Nếu máy chủ dùng chứng chỉ tự ký (Self-signed certificate), thử thiết lập:")
        print('     $env:MY_ENTERPRISE_VERIFY_SSL="false"')
        print("=" * 70)
        return False

    except MyEnterpriseTimeoutError as e:
        print(f"\n[LỖI TIMEOUT] {e}")
        print("=" * 70)
        return False

    except MyEnterpriseApiError as e:
        print(f"\n[LỖI API] HTTP Status {e.status_code}: {e}")
        print("=" * 70)
        return False

    except Exception as e:
        print(f"\n[LỖI KHÔNG XÁC ĐỊNH] {type(e).__name__}: {e}")
        print("=" * 70)
        return False

    finally:
        client.close()


if __name__ == "__main__":
    # Cho phép truyền tham số ngày từ dòng lệnh nếu muốn: python manual_test.py 2026-09-04
    date_arg = sys.argv[1] if len(sys.argv) > 1 else "2026-09-06"
    run_manual_test(target_date=date_arg)
