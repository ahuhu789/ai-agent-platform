"""Mock data for Attendance / Chuyên cần subsystem."""

# Daily records for September 2026 (working days up to current date)
MOCK_ATTENDANCE_RECORDS = [
    # NV001 - Nguyễn Văn A (Nhân viên A)
    # 18 working days, 2 late arrivals, 1 approved leave day
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

    # NV002 - Trần Thị B (Trưởng phòng Nhân sự)
    {"id": "ATT-019", "employee_id": "NV002", "employee_name": "Trần Thị B", "date": "2026-09-24", "check_in": "08:15:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
    # NV003 - Lê Hoàng C
    {"id": "ATT-020", "employee_id": "NV003", "employee_name": "Lê Hoàng C", "date": "2026-09-24", "check_in": "08:35:00", "check_out": "17:40:00", "status": "late", "work_hours": 7.9, "late_minutes": 5, "notes": "Trễ 5 phút"},
    # NV004 - Phạm Minh D
    {"id": "ATT-021", "employee_id": "NV004", "employee_name": "Phạm Minh D", "date": "2026-09-24", "check_in": "08:20:00", "check_out": "17:30:00", "status": "on_time", "work_hours": 8.0, "late_minutes": 0, "notes": "Đúng giờ"},
]

# Aggregated Monthly Summaries for Sept 2026
MOCK_MONTHLY_ATTENDANCE = {
    ("NV001", 9, 2026): {
        "employee_id": "NV001",
        "employee_name": "Nguyễn Văn A",
        "month": 9,
        "year": 2026,
        "total_working_days": 18,
        "actual_working_days": 18,  # Exactly 18 days worked this month!
        "late_count": 2,            # Exactly 2 times late!
        "early_leave_count": 0,
        "absent_count": 1,          # 1 approved leave
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
        "late_count": 1,
        "early_leave_count": 1,
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
}
