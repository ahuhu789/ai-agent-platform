"""
CLI Runner và Unified Client cho phân hệ My Enterprise Attendance.

Hỗ trợ chạy lệnh crawl thực tế từ dòng lệnh:
python -m integrations.my_enterprise_attendance.client --employees
python -m integrations.my_enterprise_attendance.client --attendance
python -m integrations.my_enterprise_attendance.client --all

QUY TẮC AN TOÀN BẢO MẬT:
- KHÔNG in token, authorization header, cookie hoặc mật khẩu.
- Real crawl chỉ chạy khi có VPN, MY_ENTERPRISE_TOKEN và quyền truy cập.
- Dữ liệu crawl lưu vào data/local/ (được .gitignore bảo vệ).
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, Any, Optional

from integrations.my_enterprise_attendance.config import MyEnterpriseConfig
from integrations.my_enterprise_attendance.employee_client import (
    EmployeeClient,
    EmployeeClientError,
    EmployeeClientConfigError,
    EmployeeClientAuthError,
    EmployeeClientConnectionError,
    EmployeeClientTimeoutError
)
from integrations.my_enterprise_attendance.attendance_client import (
    AttendanceClient,
    AttendanceClientError,
    AttendanceClientConfigError,
    AttendanceClientAuthError,
    AttendanceClientConnectionError,
    AttendanceClientTimeoutError
)
from integrations.my_enterprise_attendance.mapper import (
    normalize_attendance_response,
    normalize_attendance_record,
    normalize_employee,
    join_employee_attendance
)

# Export legacy error classes for backward compatibility
MyEnterpriseError = Exception
MyEnterpriseConfigurationError = EmployeeClientConfigError
MyEnterpriseAuthenticationError = EmployeeClientAuthError
MyEnterpriseApiError = Exception
MyEnterpriseConnectionError = EmployeeClientConnectionError
MyEnterpriseTimeoutError = EmployeeClientTimeoutError


class MyEnterpriseClient(AttendanceClient):
    """
    Unified client kế thừa AttendanceClient để duy trì tương thích ngược 100%.
    """
    def get_my_normalized_attendance(
        self,
        month_year: str,
        page: int = 0,
        size: int = 50
    ) -> Dict[str, Any]:
        raw_response = self.get_my_attendance(
            month_year=month_year,
            page=page,
            size=size
        )
        return normalize_attendance_response(raw_response)


def run_crawl_employees(config: MyEnterpriseConfig) -> list:
    print("[CRAWL] Bắt đầu trích xuất danh sách nhân viên từ Employee API...")
    client = EmployeeClient(config)
    try:
        employees = client.get_all_employees()
        print(f"[CRAWL THÀNH CÔNG] Tổng số nhân viên trích xuất được: {len(employees)}")
        return employees
    except EmployeeClientConfigError as e:
        print(f"[LỖI CẤU HÌNH] {e}")
        return []
    except EmployeeClientAuthError as e:
        print(f"[LỖI XÁC THỰC] {e}")
        return []
    except EmployeeClientConnectionError as e:
        print(f"[LỖI KẾT NỐI] {e}")
        return []
    except Exception as e:
        print(f"[LỖI] {e}")
        return []


def run_crawl_attendance(config: MyEnterpriseConfig, month_year: Optional[str] = None) -> list:
    query_time = month_year or datetime.now().strftime("%Y-%m")
    print(f"[CRAWL] Bắt đầu trích xuất dữ liệu chấm công ({query_time}) từ Attendance API...")
    print("  (LƯU Ý: Endpoint /me chỉ đại diện cho tài khoản hiện tại)")
    client = AttendanceClient(config)
    try:
        attendances = client.get_all_my_attendance(month_year=query_time)
        print(f"[CRAWL THÀNH CÔNG] Tổng số bản ghi chấm công trích xuất được: {len(attendances)}")
        return attendances
    except AttendanceClientConfigError as e:
        print(f"[LỖI CẤU HÌNH] {e}")
        return []
    except AttendanceClientAuthError as e:
        print(f"[LỖI XÁC THỰC] {e}")
        return []
    except AttendanceClientConnectionError as e:
        print(f"[LỖI KẾT NỐI] {e}")
        return []
    except Exception as e:
        print(f"[LỖI] {e}")
        return []


def main():
    if sys.platform.startswith("win"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(description="My Enterprise Web 1.18 Crawl CLI")
    parser.add_argument("--employees", action="store_true", help="Crawl dữ liệu nhân viên")
    parser.add_argument("--attendance", action="store_true", help="Crawl dữ liệu chấm công")
    parser.add_argument("--all", action="store_true", help="Crawl cả nhân viên và chấm công, thực hiện JOIN")
    parser.add_argument("--month", type=str, default=None, help="Tháng/ngày crawl chấm công (YYYY-MM hoặc YYYY-MM-DD)")

    args = parser.parse_args()

    if not (args.employees or args.attendance or args.all):
        parser.print_help()
        sys.exit(0)

    config = MyEnterpriseConfig.from_env()

    # Kiểm tra token trước khi crawl
    if not config.token:
        print("=" * 65)
        print("[THÔNG BÁO] Biến môi trường 'MY_ENTERPRISE_TOKEN' chưa được thiết lập.")
        print("Real crawl yêu cầu VPN nội bộ và Bearer Token hợp lệ.")
        print("Hệ thống sẽ chạy hoàn toàn ngoại tuyến với bộ Mock Dataset.")
        print("=" * 65)
        sys.exit(1)

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    local_dir = os.path.join(project_root, "data", "local")
    os.makedirs(local_dir, exist_ok=True)

    employees = []
    attendances = []

    if args.employees or args.all:
        employees = run_crawl_employees(config)
        if employees:
            out_file = os.path.join(local_dir, "employees_raw.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(employees, f, ensure_ascii=False, indent=2)
            print(f"[LƯU TRỮ] Đã lưu snapshot vào {out_file}")

    if args.attendance or args.all:
        attendances = run_crawl_attendance(config, args.month)
        if attendances:
            out_file = os.path.join(local_dir, "attendance_raw.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(attendances, f, ensure_ascii=False, indent=2)
            print(f"[LƯU TRỮ] Đã lưu snapshot vào {out_file}")

    if args.all or (employees and attendances):
        print("\n" + "=" * 50)
        print("   KẾT QUẢ TỔNG HỢP VÀ JOIN DỮ LIỆU")
        print("=" * 50)
        joined_records, mapped_count, unmapped_count = join_employee_attendance(employees, attendances)
        print(f"Employee count: {len(employees)}")
        print(f"Attendance record count: {len(attendances)}")
        print(f"Mapped attendance: {mapped_count}")
        print(f"Unmapped attendance: {unmapped_count}")
        out_joined = os.path.join(local_dir, "attendance_normalized.json")
        with open(out_joined, "w", encoding="utf-8") as f:
            json.dump(joined_records, f, ensure_ascii=False, indent=2)
        print(f"[LƯU TRỮ] Đã lưu normalized dataset vào {out_joined}")
        print("=" * 50)


if __name__ == "__main__":
    main()
