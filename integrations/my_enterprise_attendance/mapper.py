"""
Module ánh xạ dữ liệu (Mapper) từ định dạng phản hồi My Enterprise Web 1.18
sang cấu trúc dữ liệu chuẩn hóa nội bộ (Normalized Dataset) và thực hiện JOIN.

Quy tắc bảo mật và an toàn:
- Không crash khi thiếu trường hoặc giá trị null.
- employee_code BẮT BUỘC lấy từ codeDisplay (KHÔNG dùng id, KHÔNG tự sinh).
- JOIN giữa Attendance và Employee BẮT BUỘC dùng ID:
  attendance.employeeInfo.id == employee.id
- Tuyệt đối không JOIN bằng tên hoặc fuzzy matching.
"""

from typing import Dict, Any, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


def _extract_full_name(employee_info: Optional[Dict[str, Any]]) -> Optional[str]:
    """
    Kết hợp lastName và firstName theo quy chuẩn họ tên tiếng Việt (Họ + Tên đệm + Tên).
    Xử lý an toàn nếu một hoặc cả hai trường bị null/rỗng hoặc đã có trường name/employee_name sẵn.
    """
    if not isinstance(employee_info, dict):
        return None

    last_name = str(employee_info.get("lastName") or employee_info.get("last_name") or "").strip()
    first_name = str(employee_info.get("firstName") or employee_info.get("first_name") or "").strip()

    if last_name and first_name:
        return f"{last_name} {first_name}"
    elif last_name:
        return last_name
    elif first_name:
        return first_name

    existing_name = employee_info.get("name") or employee_info.get("employee_name")
    if existing_name:
        return str(existing_name).strip()
    return None


def normalize_employee(raw_employee: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Chuẩn hóa thông tin nhân viên từ Employee API (hoặc employeeInfo).
    Hỗ trợ cả dict raw từ API và dict đã qua lưu trữ normalized.
    
    Quy tắc bắt buộc:
    - id -> employee_id
    - codeDisplay -> employee_code (BẮT BUỘC dùng codeDisplay, KHÔNG dùng id, KHÔNG tự generate)
    - firstName -> first_name
    - lastName -> last_name
    - Ghép họ tên -> employee_name
    """
    if not isinstance(raw_employee, dict):
        return {
            "employee_id": None,
            "employee_code": None,
            "first_name": None,
            "last_name": None,
            "employee_name": None
        }

    raw_code_display = raw_employee.get("codeDisplay")
    if raw_code_display is None:
        raw_code_display = raw_employee.get("employee_code")

    if raw_code_display is not None and str(raw_code_display).strip() != "":
        emp_code = str(raw_code_display).strip()
    else:
        # Nếu không có codeDisplay / employee_code, giữ None chứ KHÔNG dùng id làm code
        emp_code = None

    raw_id = raw_employee.get("id") if raw_employee.get("id") is not None else raw_employee.get("employee_id")
    first_name = raw_employee.get("firstName") if raw_employee.get("firstName") is not None else raw_employee.get("first_name")
    last_name = raw_employee.get("lastName") if raw_employee.get("lastName") is not None else raw_employee.get("last_name")

    return {
        "employee_id": raw_id,
        "employee_code": emp_code,
        "first_name": first_name,
        "last_name": last_name,
        "employee_name": _extract_full_name(raw_employee)
    }


def normalize_attendance_record(raw_record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Chuyển đổi một bản ghi chấm công thô từ Web 1.18 sang bản ghi chuẩn hóa.
    
    Cấu trúc chuẩn hóa:
    {
        "employee_id": 16,
        "employee_code": "009",
        "employee_name": "Lê Hữu Thanh Vy",
        "date": "2026-09-04",
        "record_time": "10:19:49",
        "check_in": "10:19:49",
        "check_out": "21:19:57",
        "latitude": 10.807207964,
        "longitude": 106.628620666,
        "location": "Phường Tân Sơn Nhì, ..."
    }
    """
    if not isinstance(raw_record, dict):
        return {
            "employee_id": None,
            "employee_code": None,
            "employee_name": None,
            "date": None,
            "record_time": None,
            "check_in": None,
            "check_out": None,
            "latitude": None,
            "longitude": None,
            "location": None
        }

    employee_info = raw_record.get("employeeInfo")
    if not isinstance(employee_info, dict):
        employee_info = {}

    # Sử dụng normalize_employee để trích xuất nhất quán
    norm_emp = normalize_employee(employee_info)

    # Tọa độ latitude / longitude
    lat = raw_record.get("latitude")
    lon = raw_record.get("longitude")
    try:
        lat = float(lat) if lat is not None else None
    except (ValueError, TypeError):
        lat = None

    try:
        lon = float(lon) if lon is not None else None
    except (ValueError, TypeError):
        lon = None

    return {
        "employee_id": norm_emp["employee_id"],
        "employee_code": norm_emp["employee_code"],
        "employee_name": norm_emp["employee_name"],
        "date": raw_record.get("recordDate") or raw_record.get("date"),
        "record_time": raw_record.get("recordTime") or raw_record.get("record_time"),
        "check_in": raw_record.get("checkInTime") or raw_record.get("check_in"),
        "check_out": raw_record.get("checkOutTime") or raw_record.get("check_out"),
        "status": raw_record.get("status"),
        "notes": raw_record.get("notes"),
        "latitude": lat,
        "longitude": lon,
        "location": raw_record.get("locationName") or raw_record.get("location")
    }


def normalize_attendance_response(raw_response: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Chuẩn hóa toàn bộ phản hồi từ API Web 1.18.
    """
    if not isinstance(raw_response, dict):
        return {
            "records": [],
            "total_records": 0,
            "pagination": {}
        }

    raw_results = raw_response.get("results")
    if not isinstance(raw_results, list):
        raw_results = []

    normalized_records = [normalize_attendance_record(item) for item in raw_results]

    pagination_keys = [
        "page", "pageNumber", "size", "pageSize", "total", "totalElements",
        "totalPages", "numberOfElements", "first", "last", "empty"
    ]
    pagination_info = {
        k: raw_response[k] for k in pagination_keys if k in raw_response
    }

    return {
        "records": normalized_records,
        "total_records": len(normalized_records),
        "pagination": pagination_info
    }


def join_employee_attendance(
    employees: List[Dict[str, Any]],
    attendances: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], int, int]:
    """
    Thực hiện JOIN giữa tập Employee và Attendance bằng employee ID.
    
    Quy tắc quan trọng:
    - JOIN key: attendance.employeeInfo.id == employee.id (hoặc att['employee_id'] == emp['employee_id'])
    - Gán employee_code = employee.codeDisplay (hoặc emp['employee_code'])
    - TUYỆT ĐỐI KHÔNG JOIN bằng firstName, lastName hoặc fuzzy match.
    - Nếu không tìm thấy: đánh dấu unmapped = True và cảnh báo.
    
    Trả về:
        (joined_records, mapped_count, unmapped_count)
    """
    # 1. Xây dựng bảng tra cứu nhân viên bằng employee_id
    employee_lookup: Dict[Any, Dict[str, Any]] = {}
    for emp in employees:
        if not isinstance(emp, dict):
            continue
        # Chuẩn hóa nếu đầu vào là raw dictionary từ API
        norm_emp = normalize_employee(emp) if "codeDisplay" in emp or "firstName" in emp else emp
        emp_id = norm_emp.get("employee_id")
        if emp_id is not None:
            employee_lookup[emp_id] = norm_emp

    joined_records: List[Dict[str, Any]] = []
    mapped_count = 0
    unmapped_count = 0

    # 2. Lặp qua từng bản ghi attendance để map thông tin
    for att in attendances:
        if not isinstance(att, dict):
            continue

        # Chuẩn hóa attendance record nếu là raw
        if "recordDate" in att or "employeeInfo" in att:
            norm_att = normalize_attendance_record(att)
        else:
            norm_att = dict(att)

        att_emp_id = norm_att.get("employee_id")

        if att_emp_id is not None and att_emp_id in employee_lookup:
            emp = employee_lookup[att_emp_id]
            merged = dict(norm_att)
            # employee_code PHẢI lấy từ Employee.codeDisplay
            if emp.get("employee_code"):
                merged["employee_code"] = emp["employee_code"]
            if emp.get("employee_name"):
                merged["employee_name"] = emp["employee_name"]
            merged["unmapped"] = False
            joined_records.append(merged)
            mapped_count += 1
        else:
            merged = dict(norm_att)
            merged["unmapped"] = True
            joined_records.append(merged)
            unmapped_count += 1
            logger.warning(
                f"[MAPPER WARNING] Bản ghi chấm công ngày {merged.get('date')} có employee_id={att_emp_id} "
                f"không tìm thấy trong Employee dataset."
            )

    return joined_records, mapped_count, unmapped_count
