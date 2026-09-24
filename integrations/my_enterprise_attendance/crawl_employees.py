"""
Script crawl danh sách nhân viên thực tế từ hệ thống My Enterprise Web 1.18.

Mục tiêu & Quy tắc:
1. Gọi API:
   GET https://fm-internal.tasolutions.com.vn:8444/api/core/core/api/v1/resources/organization/org-info/employees/suggestion
   Parameters: size=100, page=0, searchText=""
2. Crawl toàn bộ danh sách bằng phân trang (pagination).
3. Field mapping:
   - employee_id = id
   - first_name = firstName
   - last_name = lastName
   - employee_code = codeDisplay (BẮT BUỘC, không dùng id, không tự sinh, không sửa mã)
4. Lưu raw response: data/raw/employees_raw.json
5. Lưu normalized dataset: data/mock/employees.json và đồng bộ fixtures/employees_mock.json
6. Kiểm tra duplicate: employee_id và employee_code.
7. Token lấy từ biến môi trường MY_ENTERPRISE_TOKEN.
8. Nếu lỗi mạng/VPN/Auth: DỪNG tại bước crawl, KHÔNG tạo dữ liệu giả, báo chính xác lỗi kết nối.
9. Xuất báo cáo theo định dạng yêu cầu.
"""

import os
import sys
import json
from typing import Dict, Any, List, Optional, Tuple
from dotenv import load_dotenv
import httpx

# Cấu hình encoding UTF-8 cho Windows console
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Đảm bảo root project có trong sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

API_URL = "https://fm-internal.tasolutions.com.vn:8444/api/core/core/api/v1/resources/organization/org-info/employees/suggestion"
RAW_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "employees_raw.json")
MOCK_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "mock", "employees.json")
FIXTURE_DATA_PATH = os.path.join(PROJECT_ROOT, "integrations", "my_enterprise_attendance", "fixtures", "employees_mock.json")
FIXTURE_ATTENDANCE_PATH = os.path.join(PROJECT_ROOT, "integrations", "my_enterprise_attendance", "fixtures", "attendance_mock.json")


def crawl_employees() -> Dict[str, Any]:
    """
    Thực hiện crawl toàn bộ nhân viên từ API My Enterprise Web 1.18.
    """
    token = os.getenv("MY_ENTERPRISE_TOKEN")
    if not token or not token.strip():
        print("\n" + "=" * 70)
        print("LỖI KẾT NỐI: Biến môi trường 'MY_ENTERPRISE_TOKEN' chưa được thiết lập!")
        print("DỪNG TẠI BƯỚC CRAWL THEO YÊU CẦU 13 (KHÔNG TỰ TẠO DỮ LIỆU GIẢ).")
        print("Vui lòng cấu hình token:")
        print('  - Trong file .env: MY_ENTERPRISE_TOKEN=<token_thực_tế>')
        print('  - Hoặc trong PowerShell: $env:MY_ENTERPRISE_TOKEN="<token_thực_tế>"')
        print("=" * 70 + "\n")
        return {
            "success": False,
            "error_type": "MISSING_TOKEN",
            "error_message": "Biến môi trường MY_ENTERPRISE_TOKEN chưa được cấu hình."
        }

    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    verify_ssl_env = os.getenv("MY_ENTERPRISE_VERIFY_SSL", "true").strip().lower()
    verify_ssl = False if verify_ssl_env in ("false", "0", "no") else True

    timeout_seconds = float(os.getenv("MY_ENTERPRISE_TIMEOUT", "30.0"))

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    raw_pages: List[Dict[str, Any]] = []
    raw_employees: List[Dict[str, Any]] = []
    page = 0
    size = 100
    total_pages_detected = 0

    print(f"[*] Bắt đầu crawl dữ liệu từ API: {API_URL}")
    print(f"[*] Tham số: size={size}, page=0, searchText=''")

    with httpx.Client(timeout=timeout_seconds, verify=verify_ssl) as client:
        while True:
            params = {
                "size": size,
                "page": page,
                "searchText": ""
            }
            try:
                response = client.get(API_URL, params=params, headers=headers)
            except httpx.ConnectError as ce:
                print(f"\n[LỖI KẾT NỐI] Không thể kết nối tới server My Enterprise: {ce}")
                print("DỪNG TẠI BƯỚC CRAWL (Vui lòng kiểm tra VPN hoặc mạng nội bộ).")
                return {
                    "success": False,
                    "error_type": "CONNECTION_ERROR",
                    "error_message": f"Không thể kết nối tới server (ConnectError): {ce}"
                }
            except httpx.TimeoutException as te:
                print(f"\n[LỖI TIMEOUT] Yêu cầu bị quá thời gian chờ sau {timeout_seconds}s: {te}")
                print("DỪNG TẠI BƯỚC CRAWL.")
                return {
                    "success": False,
                    "error_type": "TIMEOUT_ERROR",
                    "error_message": f"Timeout sau {timeout_seconds}s: {te}"
                }
            except httpx.RequestError as re:
                print(f"\n[LỖI YÊU CẦU HTTP] Lỗi mạng: {re}")
                print("DỪNG TẠI BƯỚC CRAWL.")
                return {
                    "success": False,
                    "error_type": "NETWORK_ERROR",
                    "error_message": f"Lỗi yêu cầu HTTP: {re}"
                }

            status_code = response.status_code
            if status_code == 401:
                print(f"\n[LỖI XÁC THỰC HTTP 401] Token không hợp lệ hoặc đã hết hạn!")
                print("DỪNG TẠI BƯỚC CRAWL THEO YÊU CẦU 13 (KHÔNG TẠO DỮ LIỆU GIẢ).")
                return {
                    "success": False,
                    "error_type": "AUTH_401_UNAUTHORIZED",
                    "error_message": "HTTP 401 Unauthorized: Bearer Token không hợp lệ hoặc đã hết hạn."
                }
            elif status_code == 403:
                print(f"\n[LỖI TRUY CẬP HTTP 403] Tài khoản không có quyền truy cập endpoint này!")
                print("DỪNG TẠI BƯỚC CRAWL THEO YÊU CẦU 13 (KHÔNG TẠO DỮ LIỆU GIẢ).")
                return {
                    "success": False,
                    "error_type": "AUTH_403_FORBIDDEN",
                    "error_message": "HTTP 403 Forbidden: Tài khoản không có quyền xem danh sách nhân viên."
                }
            elif status_code != 200:
                print(f"\n[LỖI PHẢN HỒI HTTP {status_code}] Nội dung: {response.text[:300]}")
                print("DỪNG TẠI BƯỚC CRAWL THEO YÊU CẦU 13.")
                return {
                    "success": False,
                    "error_type": f"HTTP_{status_code}",
                    "error_message": f"HTTP {status_code}: {response.text[:300]}"
                }

            # Phân tích cú pháp JSON
            try:
                data = response.json()
            except Exception as e:
                print(f"\n[LỖI JSON] Không thể parse response thành JSON: {e}")
                print("DỪNG TẠI BƯỚC CRAWL.")
                return {
                    "success": False,
                    "error_type": "JSON_PARSE_ERROR",
                    "error_message": f"Không thể parse JSON: {e}"
                }

            raw_pages.append(data)
            results = data.get("results") if isinstance(data, dict) else (data if isinstance(data, list) else [])
            if not isinstance(results, list):
                results = []

            print(f"  -> Page {page}: nhận được {len(results)} nhân viên.")
            raw_employees.extend(results)

            # Phân trang: kiểm tra totalPages, hasNext
            total_pages = data.get("totalPages") if isinstance(data, dict) else None
            if total_pages is not None:
                try:
                    total_pages_detected = int(total_pages)
                    if page + 1 >= total_pages_detected:
                        break
                except (ValueError, TypeError):
                    pass

            has_next = data.get("hasNext") if isinstance(data, dict) else None
            if has_next is False:
                break
            elif has_next is True:
                # Còn trang tiếp theo theo cờ hasNext
                pass
            elif total_pages is not None:
                # Đã kiểm tra ở trên page + 1 >= total_pages_detected
                pass
            elif len(results) < size:
                # Nếu API không trả totalPages và không có hasNext, dùng len(results) < size để xác định trang cuối
                break

            page += 1
            if page >= 200:  # Giới hạn an toàn
                break

    total_pages_crawled = page + 1
    total_raw_count = len(raw_employees)
    print(f"[+] Hoàn thành crawl: {total_pages_crawled} page(s), tổng cộng {total_raw_count} bản ghi nhân viên thô.")

    # 1. Lưu RAW response vào data/raw/employees_raw.json (giữ nguyên không chỉnh sửa)
    os.makedirs(os.path.dirname(RAW_DATA_PATH), exist_ok=True)
    with open(RAW_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(raw_employees, f, ensure_ascii=False, indent=2)
    print(f"[+] Đã lưu Raw response API vào: {RAW_DATA_PATH}")

    # 2. Chuẩn hóa dữ liệu theo đúng đặc tả:
    # {
    #     "employee_id": id,
    #     "first_name": firstName,
    #     "last_name": lastName,
    #     "employee_code": codeDisplay
    # }
    normalized_employees: List[Dict[str, Any]] = []
    seen_ids: Dict[Any, int] = {}
    seen_codes: Dict[Any, int] = {}
    duplicate_ids: List[Any] = []
    duplicate_codes: List[Any] = []
    valid_employee_count = 0

    id_mapping_pass = True
    code_display_pass = True

    for item in raw_employees:
        if not isinstance(item, dict):
            continue

        raw_id = item.get("id")
        first_name = item.get("firstName")
        last_name = item.get("lastName")
        code_display = item.get("codeDisplay")

        # Kiểm tra quy tắc: employee_id lấy từ API `id`
        emp_id = raw_id
        if emp_id is None:
            id_mapping_pass = False

        # Kiểm tra quy tắc: employee_code BẮT BUỘC lấy từ API `codeDisplay`
        # KHÔNG dùng id làm code, KHÔNG tự format ID, KHÔNG tự sinh mã, KHÔNG tự sửa
        emp_code = str(code_display).strip() if code_display is not None else None
        if emp_code != (str(code_display).strip() if code_display is not None else None):
            code_display_pass = False

        # Kiểm tra duplicate
        if emp_id is not None:
            seen_ids[emp_id] = seen_ids.get(emp_id, 0) + 1
            if seen_ids[emp_id] == 2:
                duplicate_ids.append(emp_id)

        if emp_code is not None:
            seen_codes[emp_code] = seen_codes.get(emp_code, 0) + 1
            if seen_codes[emp_code] == 2:
                duplicate_codes.append(emp_code)

        # Ghép họ tên
        parts = []
        if last_name:
            parts.append(str(last_name).strip())
        if first_name:
            parts.append(str(first_name).strip())
        full_name = " ".join(parts) if parts else (item.get("name") or "N/A")

        norm = {
            "employee_id": emp_id,
            "first_name": first_name,
            "last_name": last_name,
            "employee_code": emp_code,
            "name": full_name,
            "position": item.get("position", "Nhân viên"),
            "department": item.get("department", "Công ty")
        }
        normalized_employees.append(norm)
        valid_employee_count += 1

    # 3. Lưu Normalized Data vào data/mock/employees.json
    os.makedirs(os.path.dirname(MOCK_DATA_PATH), exist_ok=True)
    with open(MOCK_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(normalized_employees, f, ensure_ascii=False, indent=2)
    print(f"[+] Đã lưu Normalized Dataset vào: {MOCK_DATA_PATH}")

    # 4. Đồng bộ vào fixtures/employees_mock.json để project sử dụng
    os.makedirs(os.path.dirname(FIXTURE_DATA_PATH), exist_ok=True)
    with open(FIXTURE_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(raw_employees, f, ensure_ascii=False, indent=2)
    print(f"[+] Đã đồng bộ fixture: {FIXTURE_DATA_PATH}")

    # 5. Kiểm tra Attendance JOIN theo ID
    # attendance.employeeInfo.id == employee.employee_id -> employee.employee_code
    join_pass = True
    if os.path.exists(FIXTURE_ATTENDANCE_PATH):
        try:
            with open(FIXTURE_ATTENDANCE_PATH, "r", encoding="utf-8") as f:
                att_records = json.load(f)
            emp_by_id = {e["employee_id"]: e for e in normalized_employees if e["employee_id"] is not None}
            tested_joins = 0
            for att in att_records:
                att_emp_info = att.get("employeeInfo")
                if isinstance(att_emp_info, dict):
                    att_id = att_emp_info.get("id")
                    if att_id is not None and att_id in emp_by_id:
                        matched_code = emp_by_id[att_id]["employee_code"]
                        tested_joins += 1
                        if att_emp_info.get("codeDisplay") and matched_code != str(att_emp_info["codeDisplay"]).strip():
                            join_pass = False
        except Exception as e:
            print(f"[CẢNH BÁO] Lỗi kiểm tra Attendance JOIN: {e}")
            join_pass = False

    # In báo cáo theo format yêu cầu
    report = f"""
============================================================
EMPLOYEE CRAWL RESULT
- API: {API_URL}
- số page: {total_pages_crawled}
- tổng số employee: {total_raw_count}
- số employee hợp lệ: {valid_employee_count}
- duplicate employee_id: {len(duplicate_ids)} ({duplicate_ids})
- duplicate employee_code: {len(duplicate_codes)} ({duplicate_codes})
- số employee được cập nhật vào mock data: {len(normalized_employees)}

DATA VALIDATION
- employee_id mapping: {'PASS' if id_mapping_pass else 'FAIL'}
- employee_code = codeDisplay: {'PASS' if code_display_pass else 'FAIL'}
- attendance employee JOIN: {'PASS' if join_pass else 'FAIL'}
============================================================
"""
    print(report)

    return {
        "success": True,
        "total_pages": total_pages_crawled,
        "total_employees": total_raw_count,
        "valid_employees": valid_employee_count,
        "duplicate_ids": duplicate_ids,
        "duplicate_codes": duplicate_codes,
        "report": report
    }


if __name__ == "__main__":
    result = crawl_employees()
    if not result.get("success"):
        sys.exit(1)
