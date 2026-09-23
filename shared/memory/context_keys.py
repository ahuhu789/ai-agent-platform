"""Tên key chuẩn cho context, để các Agent dùng thống nhất.

Ví dụ: Employee Agent ghi ``LAST_EMPLOYEE_ID`` sau khi tìm nhân viên; sau đó
Attendance Agent đọc lại để hiểu "người đó" là ai.
Chỉ chứa hằng số, không chứa business logic.
"""

# Context chung (user context)
LAST_EMPLOYEE_ID = "last_mentioned_employee_id"
LAST_EMPLOYEE_NAME = "last_mentioned_employee_name"
LAST_CANDIDATE_ID = "last_mentioned_candidate_id"
LAST_DEPARTMENT = "last_mentioned_department"
LAST_AGENT = "last_agent"

# Context riêng Agent (agent context)
LAST_MONTH = "last_month"
LAST_FROM_DATE = "last_from_date"
LAST_TO_DATE = "last_to_date"
