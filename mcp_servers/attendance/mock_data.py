"""Mock data for Attendance / Chuyên cần subsystem (FME Enterprise)."""

# Comprehensive daily records for September and August 2026
MOCK_ATTENDANCE_RECORDS = [
    # --- NV001: Nguyễn Văn A (Nhân viên A) ---
    # September 2026: 18 working days, 2 late arrivals, 1 approved leave
    {"id": "ATT-001", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-01", "check_in": "08:25:00", "check_out": "17:35:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-002", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-02", "check_in": "08:28:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-003", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-03", "check_in": "08:45:00", "check_out": "17:45:00", "status": "late", "work_hours": 7.75, "late_minutes": 15, "notes": "Kẹt xe cầu vượt"},
    {"id": "ATT-004", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-04", "check_in": "08:20:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-005", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-07", "check_in": "08:22:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-006", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-08", "check_in": "08:29:00", "check_out": "17:31:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-007", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-09", "check_in": "08:15:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-008", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-10", "check_in": "08:50:00", "check_out": "18:00:00", "status": "late", "work_hours": 7.6, "late_minutes": 20, "notes": "Mưa to ngập đường"},
    {"id": "ATT-009", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-11", "check_in": "08:24:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-010", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-14", "check_in": "08:18:00", "check_out": "17:35:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-011", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-15", "check_in": "08:20:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-012", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-16", "check_in": "08:25:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-013", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-17", "check_in": "08:21:00", "check_out": "17:32:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-014", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-18", "check_in": None, "check_out": None, "status": "absent", "work_hours": 0.0, "late_minutes": 0, "notes": "Nghỉ phép năm có đơn"},
    {"id": "ATT-015", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-21", "check_in": "08:19:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-016", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-22", "check_in": "08:26:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-017", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-23", "check_in": "08:22:00", "check_out": "17:35:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-018", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-09-24", "check_in": "08:25:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    # NV001 - August 2026 records sample
    {"id": "ATT-019", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-08-03", "check_in": "08:20:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-020", "employee_id": "NV001", "employee_name": "Nguyễn Văn A", "date": "2026-08-14", "check_in": "08:40:00", "check_out": "17:40:00", "status": "late", "work_hours": 7.8, "late_minutes": 10, "notes": "Trễ 10 phút"},

    # --- NV002: Trần Thị B (Nhân viên B) ---
    {"id": "ATT-021", "employee_id": "NV002", "employee_name": "Trần Thị B", "date": "2026-09-01", "check_in": "08:15:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-022", "employee_id": "NV002", "employee_name": "Trần Thị B", "date": "2026-09-10", "check_in": "08:18:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    {"id": "ATT-023", "employee_id": "NV002", "employee_name": "Trần Thị B", "date": "2026-09-24", "check_in": "08:15:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},

    # --- NV003: Lê Hoàng C ---
    {"id": "ATT-024", "employee_id": "NV003", "employee_name": "Lê Hoàng C", "date": "2026-09-03", "check_in": "08:45:00", "check_out": "17:45:00", "status": "late", "work_hours": 7.75, "late_minutes": 15, "notes": "Trễ 15 phút"},
    {"id": "ATT-025", "employee_id": "NV003", "employee_name": "Lê Hoàng C", "date": "2026-09-15", "check_in": None, "check_out": None, "status": "absent", "work_hours": 0.0, "late_minutes": 0, "notes": "Khám sức khỏe định kỳ"},
    {"id": "ATT-026", "employee_id": "NV003", "employee_name": "Lê Hoàng C", "date": "2026-09-24", "check_in": "08:35:00", "check_out": "17:40:00", "status": "late", "work_hours": 7.9, "late_minutes": 5, "notes": "Trễ 5 phút"},

    # --- NV004: Phạm Minh D ---
    {"id": "ATT-027", "employee_id": "NV004", "employee_name": "Phạm Minh D", "date": "2026-09-08", "check_in": "08:40:00", "check_out": "17:40:00", "status": "late", "work_hours": 7.8, "late_minutes": 10, "notes": "Trễ 10 phút"},
    {"id": "ATT-028", "employee_id": "NV004", "employee_name": "Phạm Minh D", "date": "2026-09-24", "check_in": "08:20:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},

    # --- NV005: Vũ Hải E ---
    {"id": "ATT-029", "employee_id": "NV005", "employee_name": "Vũ Hải E", "date": "2026-09-24", "check_in": "08:22:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},

    # --- NV006: Đỗ Thị F ---
    {"id": "ATT-030", "employee_id": "NV006", "employee_name": "Đỗ Thị F", "date": "2026-09-24", "check_in": "08:18:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},

    # --- NV007: Bùi Văn G ---
    {"id": "ATT-031", "employee_id": "NV007", "employee_name": "Bùi Văn G", "date": "2026-09-24", "check_in": "08:29:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},

    # --- NV008: Hoàng Thu H ---
    {"id": "ATT-032", "employee_id": "NV008", "employee_name": "Hoàng Thu H", "date": "2026-09-24", "check_in": "08:21:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},

    # --- NV009: Ngô Quang I ---
    {"id": "ATT-033", "employee_id": "NV009", "employee_name": "Ngô Quang I", "date": "2026-09-24", "check_in": "08:10:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},

    # --- NV010: Đặng Mai K (Vắng mặt ngày 2026-09-24) ---
    {"id": "ATT-034", "employee_id": "NV010", "employee_name": "Đặng Mai K", "date": "2026-09-24", "check_in": None, "check_out": None, "status": "absent", "work_hours": 0.0, "late_minutes": 0, "notes": "Nghỉ phép năm đi công tác nước ngoài"},

    # --- NV011: Trịnh Quốc L (Đi trễ ngày 2026-09-24) ---
    {"id": "ATT-035", "employee_id": "NV011", "employee_name": "Trịnh Quốc L", "date": "2026-09-24", "check_in": "08:40:00", "check_out": "17:40:00", "status": "late", "work_hours": 7.8, "late_minutes": 10, "notes": "Trễ 10 phút"},
]

# Pre-aggregated Monthly Summaries for August & September 2026
MOCK_MONTHLY_ATTENDANCE = {
    # Tháng 9/2026 (Tính đến 24/09/2026: 18 ngày làm việc)
    ("NV001", 9, 2026): {
        "employee_id": "NV001",
        "employee_name": "Nguyễn Văn A",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 18,
        "late_count": 2,
        "early_leave_count": 0,
        "absent_count": 1,
        "attendance_rate": 94.4,
    },
    ("NV002", 9, 2026): {
        "employee_id": "NV002",
        "employee_name": "Trần Thị B",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 18,
        "late_count": 0,
        "early_leave_count": 0,
        "absent_count": 0,
        "attendance_rate": 100.0,
    },
    ("NV003", 9, 2026): {
        "employee_id": "NV003",
        "employee_name": "Lê Hoàng C",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 17,
        "late_count": 2,
        "early_leave_count": 0,
        "absent_count": 1,
        "attendance_rate": 88.9,
    },
    ("NV004", 9, 2026): {
        "employee_id": "NV004",
        "employee_name": "Phạm Minh D",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 18,
        "late_count": 1,
        "early_leave_count": 0,
        "absent_count": 0,
        "attendance_rate": 100.0,
    },
    ("NV005", 9, 2026): {
        "employee_id": "NV005",
        "employee_name": "Vũ Hải E",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 18,
        "late_count": 0,
        "early_leave_count": 0,
        "absent_count": 0,
        "attendance_rate": 100.0,
    },
    ("NV006", 9, 2026): {
        "employee_id": "NV006",
        "employee_name": "Đỗ Thị F",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 18,
        "late_count": 0,
        "early_leave_count": 0,
        "absent_count": 0,
        "attendance_rate": 100.0,
    },
    ("NV007", 9, 2026): {
        "employee_id": "NV007",
        "employee_name": "Bùi Văn G",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 18,
        "late_count": 1,
        "early_leave_count": 0,
        "absent_count": 0,
        "attendance_rate": 100.0,
    },
    ("NV008", 9, 2026): {
        "employee_id": "NV008",
        "employee_name": "Hoàng Thu H",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 18,
        "late_count": 0,
        "early_leave_count": 0,
        "absent_count": 0,
        "attendance_rate": 100.0,
    },
    ("NV009", 9, 2026): {
        "employee_id": "NV009",
        "employee_name": "Ngô Quang I",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 18,
        "late_count": 0,
        "early_leave_count": 0,
        "absent_count": 0,
        "attendance_rate": 100.0,
    },
    ("NV010", 9, 2026): {
        "employee_id": "NV010",
        "employee_name": "Đặng Mai K",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 17,
        "late_count": 0,
        "early_leave_count": 0,
        "absent_count": 1,
        "attendance_rate": 94.4,
    },

    # Tháng 8/2026 (22 ngày làm việc cả tháng)
    ("NV001", 8, 2026): {
        "employee_id": "NV001",
        "employee_name": "Nguyễn Văn A",
        "month": 8,
        "year": 2026,
        "total_working_days": 22,
        "actual_working_days": 22,
        "late_count": 1,
        "early_leave_count": 0,
        "absent_count": 0,
        "attendance_rate": 100.0,
    },
    ("NV002", 8, 2026): {
        "employee_id": "NV002",
        "employee_name": "Trần Thị B",
        "month": 8,
        "year": 2026,
        "total_working_days": 22,
        "actual_working_days": 22,
        "late_count": 0,
        "early_leave_count": 0,
        "absent_count": 0,
        "attendance_rate": 100.0,
    },
    ("NV003", 8, 2026): {
        "employee_id": "NV003",
        "employee_name": "Lê Hoàng C",
        "month": 8,
        "year": 2026,
        "total_working_days": 22,
        "actual_working_days": 21,
        "late_count": 1,
        "early_leave_count": 0,
        "absent_count": 1,
        "attendance_rate": 95.5,
    },
}

MOCK_LEAVE_REQUESTS = [
    {
        "id": "LR-001",
        "employee_id": "NV001",
        "employee_name": "Nguyễn Văn A",
        "leave_type": "Nghỉ phép năm",
        "from_date": "2026-09-18",
        "to_date": "2026-09-18",
        "days": 1,
        "status": "approved",
        "reason": "Giải quyết việc cá nhân gia đình",
        "approved_by": "Ngô Quang I",
    },
    {
        "id": "LR-002",
        "employee_id": "NV010",
        "employee_name": "Đặng Mai K",
        "leave_type": "Nghỉ phép năm",
        "from_date": "2026-09-24",
        "to_date": "2026-09-25",
        "days": 2,
        "status": "approved",
        "reason": "Đi công tác nước ngoài kết hợp nghỉ phép",
        "approved_by": "Ngô Quang I",
    },
    {
        "id": "LR-003",
        "employee_id": "NV003",
        "employee_name": "Lê Hoàng C",
        "leave_type": "Nghỉ ốm",
        "from_date": "2026-09-15",
        "to_date": "2026-09-15",
        "days": 1,
        "status": "approved",
        "reason": "Khám sức khỏe định kỳ",
        "approved_by": "Trần Thị B",
    },
]
