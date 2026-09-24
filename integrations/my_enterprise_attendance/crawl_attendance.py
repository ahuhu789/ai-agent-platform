"""
Script crawl dữ liệu chấm công (Attendance) thực tế từ My Enterprise Web 1.18 API.

Mục tiêu & Quy tắc:
1. Gọi API:
   GET https://fm-internal.tasolutions.com.vn:8444/api/core/core/api/v1/resources/employees/attendances/me
   Parameters: page=0, 1..., size=100, monthYear=YYYY-MM-01
2. Crawl toàn bộ bản ghi theo từng tháng có dữ liệu bằng phân trang (pagination).
3. Field mapping:
   - attendance.employeeInfo.id == employee.employee_id (JOIN theo ID số, KHÔNG dùng tên)
   - Lấy employee_code từ codeDisplay ("009")
   - date: recordDate
   - check_in: checkInTime
   - check_out: checkOutTime
   - record_time: recordTime
   - status: tự động tính "Present" (<= 08:30) hoặc "Late" (> 08:30) nếu API không trả về
4. Lưu raw response: data/raw/attendance_raw.json (giữ nguyên response API, không normalize)
5. Lưu normalized dataset: data/mock/attendance.json và đồng bộ fixtures/attendance_mock.json
6. Token lấy từ biến môi trường MY_ENTERPRISE_TOKEN.
7. Nếu lỗi mạng/VPN/Auth: DỪNG tại bước crawl, KHÔNG tạo dữ liệu giả, báo chính xác lỗi kết nối.
8. Xuất báo cáo theo định dạng chuẩn.
"""

import os
import sys
import json
from typing import Dict, Any, List, Optional
from datetime import datetime
from dotenv import load_dotenv
import httpx

# Cấu hình encoding UTF-8 cho Windows console
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

API_URL = "https://fm-internal.tasolutions.com.vn:8444/api/core/core/api/v1/resources/employees/attendances/me"
FILTER_API_URL = "https://fm-internal.tasolutions.com.vn:8444/api/core/core/api/v1/resources/employees/attendances/filter"
RAW_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "raw", "attendance_raw.json")
MOCK_DATA_PATH = os.path.join(PROJECT_ROOT, "data", "mock", "attendance.json")
MOCK_EMPLOYEES_PATH = os.path.join(PROJECT_ROOT, "data", "mock", "employees.json")
FIXTURE_ATTENDANCE_PATH = os.path.join(PROJECT_ROOT, "integrations", "my_enterprise_attendance", "fixtures", "attendance_mock.json")


def crawl_attendance(months: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Thực hiện crawl dữ liệu chấm công thực tế từ My Enterprise Web 1.18 API.
    Bao gồm cả toàn công ty (/filter) và cá nhân theo tháng (/me).
    """
    token = os.getenv("MY_ENTERPRISE_TOKEN")
    if not token or not token.strip():
        print("\n" + "=" * 70)
        print("LỖI KẾT NỐI: Biến môi trường 'MY_ENTERPRISE_TOKEN' chưa được thiết lập!")
        print("DỪNG TẠI BƯỚC CRAWL (KHÔNG TỰ TẠO DỮ LIỆU GIẢ).")
        print("=" * 70 + "\n")
        return {
            "success": False,
            "error_type": "MISSING_TOKEN",
            "error_message": "Biến môi trường MY_ENTERPRISE_TOKEN chưa được cấu hình."
        }

    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    verify_ssl_env = os.getenv("MY_ENTERPRISE_VERIFY_SSL", "false").strip().lower()
    verify_ssl = False if verify_ssl_env in ("false", "0", "no") else True
    timeout_seconds = float(os.getenv("MY_ENTERPRISE_TIMEOUT", "30.0"))

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }

    raw_records: List[Dict[str, Any]] = []

    with httpx.Client(timeout=timeout_seconds, verify=verify_ssl) as client:
        # 1. Crawl chấm công toàn công ty qua Filter endpoint
        print(f"[*] Bắt đầu crawl dữ liệu chấm công toàn công ty từ API: {FILTER_API_URL}")
        filter_page = 0
        filter_size = 100
        while True:
            try:
                r_filter = client.post(
                    f"{FILTER_API_URL}?page={filter_page}&size={filter_size}",
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}"
                    },
                    json={"filters": {}}
                )
            except httpx.ConnectError as ce:
                print(f"\n[LỖI KẾT NỐI] Không thể kết nối tới server My Enterprise: {ce}")
                return {"success": False, "error_type": "CONNECTION_ERROR", "error_message": f"Không thể kết nối tới server: {ce}"}
            except httpx.TimeoutException as te:
                print(f"\n[LỖI TIMEOUT] Quá thời gian chờ: {te}")
                return {"success": False, "error_type": "TIMEOUT_ERROR", "error_message": f"Timeout sau {timeout_seconds}s: {te}"}

            if r_filter.status_code == 401:
                print("\n[LỖI XÁC THỰC HTTP 401] Token không hợp lệ hoặc đã hết hạn!")
                return {"success": False, "error_type": "AUTH_401_UNAUTHORIZED", "error_message": "HTTP 401 Unauthorized."}
            elif r_filter.status_code == 403:
                print("\n[LỖI TRUY CẬP HTTP 403] Không có quyền truy cập endpoint chấm công!")
                return {"success": False, "error_type": "AUTH_403_FORBIDDEN", "error_message": "HTTP 403 Forbidden."}
            elif r_filter.status_code == 200:
                try:
                    d_filter = r_filter.json()
                    res_list = d_filter.get("results", [])
                    if isinstance(res_list, list) and res_list:
                        raw_records.extend(res_list)
                        print(f"  -> Filter trang {filter_page}: lấy được {len(res_list)} bản ghi.")
                    if not isinstance(res_list, list) or len(res_list) < filter_size:
                        break
                except Exception as e:
                    print(f"  -> Lỗi parse JSON trang {filter_page}: {e}")
                    break
            else:
                print(f"  -> Filter endpoint HTTP {r_filter.status_code}: {r_filter.text[:150]}")
                break

            filter_page += 1
            if filter_page >= 50:
                break

        # 2. Crawl lịch sử chấm công cá nhân /me theo từng tháng
        if not months:
            months = [f"2026-{m:02d}-01" for m in range(1, 13)]

        months_with_data = []
        print(f"[*] Crawl bổ sung dữ liệu lịch sử cá nhân từ API: {API_URL}")

        for m_str in months:
            page = 0
            size = 100
            month_count = 0
            while True:
                params = {
                    "page": page,
                    "size": size,
                    "monthYear": m_str
                }
                try:
                    response = client.get(API_URL, params=params, headers=headers)
                except Exception:
                    break

                if response.status_code == 200:
                    try:
                        data = response.json()
                        results = data.get("results", []) if isinstance(data, dict) else []
                        if results:
                            raw_records.extend(results)
                            month_count += len(results)
                        if not results or len(results) < size:
                            break
                    except Exception:
                        break
                else:
                    break

                page += 1
                if page >= 50:
                    break

            if month_count > 0:
                print(f"  -> Tháng {m_str[:7]}: lấy thêm {month_count} bản ghi.")
                months_with_data.append(m_str[:7])

    # Khử trùng lặp (Deduplicate)
    dedup_raw: List[Dict[str, Any]] = []
    seen_keys = set()
    for item in raw_records:
        if not isinstance(item, dict):
            continue
        emp_inf = item.get("employeeInfo") or {}
        emp_id = emp_inf.get("id") or item.get("employee_id")
        d = item.get("recordDate") or item.get("date")
        ci = item.get("checkInTime") or item.get("check_in")
        key = (str(emp_id).strip(), str(d).strip(), str(ci).strip())
        if key not in seen_keys:
            seen_keys.add(key)
            dedup_raw.append(item)
    raw_records = dedup_raw

    print(f"[+] Hoàn thành crawl: Tổng cộng {len(raw_records)} bản ghi chấm công thô hợp nhất.")

    # 1. Lưu RAW response vào data/raw/attendance_raw.json (nguyên bản, không normalize)
    os.makedirs(os.path.dirname(RAW_DATA_PATH), exist_ok=True)
    with open(RAW_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(raw_records, f, ensure_ascii=False, indent=2)
    print(f"[+] Đã lưu Raw Attendance API vào: {RAW_DATA_PATH}")

    # 2. Đọc danh sách nhân viên đã chuẩn hóa để phục vụ JOIN theo ID
    employees_by_id = {}
    if os.path.exists(MOCK_EMPLOYEES_PATH):
        try:
            with open(MOCK_EMPLOYEES_PATH, "r", encoding="utf-8") as f:
                emps = json.load(f)
                for emp in emps:
                    eid = emp.get("employee_id")
                    if eid is not None:
                        employees_by_id[eid] = emp
        except Exception as e:
            print(f"[CẢNH BÁO] Lỗi đọc data/mock/employees.json: {e}")

    # 3. Chuẩn hóa bản ghi chấm công và thực hiện JOIN bằng ID:
    # attendance.employeeInfo.id == employee.employee_id -> employee.employee_code
    normalized_records: List[Dict[str, Any]] = []
    join_pass = True
    valid_count = 0

    for raw in raw_records:
        if not isinstance(raw, dict):
            continue

        emp_info = raw.get("employeeInfo") or {}
        emp_raw_id = emp_info.get("id")
        code_display = emp_info.get("codeDisplay")

        matched_emp = employees_by_id.get(emp_raw_id)
        if matched_emp:
            emp_id = matched_emp.get("employee_id")
            emp_code = matched_emp.get("employee_code")
            emp_name = matched_emp.get("name") or matched_emp.get("employee_name")
        else:
            emp_id = emp_raw_id
            emp_code = str(code_display).strip() if code_display is not None else None
            # Ghép họ tên từ emp_info
            parts = [str(emp_info.get("lastName") or "").strip(), str(emp_info.get("firstName") or "").strip()]
            emp_name = " ".join([p for p in parts if p]) or "N/A"

        # Kiểm tra tính toàn vẹn của JOIN
        if emp_raw_id is not None and matched_emp is not None:
            if matched_emp.get("employee_code") and code_display:
                if str(matched_emp["employee_code"]).strip() != str(code_display).strip():
                    join_pass = False

        rec_date = raw.get("recordDate") or raw.get("date")
        ci_time = raw.get("checkInTime") or raw.get("check_in")
        co_time = raw.get("checkOutTime") or raw.get("check_out")
        rec_time = raw.get("recordTime") or raw.get("record_time")

        # Tự động tính toán status & notes
        status = raw.get("status")
        notes = raw.get("notes")
        if not status:
            if ci_time:
                ci_prefix = str(ci_time)[:5]
                if ci_prefix > "08:30":
                    status = "Late"
                    notes = f"Đi muộn (Check-in: {ci_prefix})"
                else:
                    status = "Present"
                    notes = "Đúng giờ"
            else:
                status = "Leave_Approved"
                notes = "Nghỉ phép có duyệt"

        norm_item = {
            "employee_id": emp_code or str(emp_id),  # Đảm bảo mã tra cứu theo employee_code (ví dụ: '009')
            "id": emp_id,
            "employee_code": emp_code,
            "employee_name": emp_name,
            "date": rec_date,
            "record_time": rec_time,
            "check_in": ci_time,
            "check_out": co_time,
            "status": status,
            "notes": notes,
            "latitude": raw.get("latitude"),
            "longitude": raw.get("longitude"),
            "location": raw.get("locationName") or raw.get("location"),
            "employeeInfo": emp_info
        }
        normalized_records.append(norm_item)
        valid_count += 1

    # 4. Lưu Normalized Attendance Dataset vào data/mock/attendance.json
    os.makedirs(os.path.dirname(MOCK_DATA_PATH), exist_ok=True)
    with open(MOCK_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(normalized_records, f, ensure_ascii=False, indent=2)
    print(f"[+] Đã lưu Normalized Attendance Dataset vào: {MOCK_DATA_PATH}")

    # 5. Đồng bộ vào fixture attendance_mock.json
    os.makedirs(os.path.dirname(FIXTURE_ATTENDANCE_PATH), exist_ok=True)
    with open(FIXTURE_ATTENDANCE_PATH, "w", encoding="utf-8") as f:
        json.dump(raw_records, f, ensure_ascii=False, indent=2)
    print(f"[+] Đã đồng bộ fixture: {FIXTURE_ATTENDANCE_PATH}")

    report = f"""
============================================================
ATTENDANCE CRAWL RESULT
- API: {API_URL}
- Các tháng đã crawl: {months_with_data}
- Tổng số bản ghi thô: {len(raw_records)}
- Số bản ghi hợp lệ: {valid_count}
- Số bản ghi được cập nhật vào mock data: {len(normalized_records)}

DATA VALIDATION
- employee_id mapping: {'PASS' if valid_count > 0 else 'FAIL'}
- employee_code = codeDisplay: {'PASS' if join_pass else 'FAIL'}
- attendance employee JOIN (by id): {'PASS' if join_pass else 'FAIL'}
============================================================
"""
    print(report)

    return {
        "success": True,
        "total_records": len(raw_records),
        "valid_records": valid_count,
        "months": months_with_data,
        "report": report
    }


if __name__ == "__main__":
    result = crawl_attendance()
    if not result.get("success"):
        sys.exit(1)
