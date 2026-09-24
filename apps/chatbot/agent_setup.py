"""
Khởi tạo AgentRegistry + RootAgent dùng chung cho toàn Chat API.

PHỤ THUỘC QUAN TRỌNG: agents/root/root_agent.py và agents/root/agent_registry.py
hiện đang nằm ở branch `feature/tra-my-root-agent`, CHƯA merge vào `main`.
Cần merge (hoặc cherry-pick 2 file này) trước khi chạy Chat API, nếu không sẽ
gặp ImportError ngay khi khởi động.
"""
from agents.root.agent_registry import AgentRegistry
from agents.root.root_agent import RootAgent
from agents.hiring.hiring_agent import HiringAgent


def build_root_agent() -> RootAgent:
    registry = AgentRegistry()

    # Hiring: đã có Agent thật -> đăng ký trực tiếp.
    registry.register(HiringAgent())

    # Attendance / Employee: chưa có Agent thật trên main.
    # KHÔNG đăng ký Mock ở đây để tránh Chat API trả lời "giả" mà người dùng
    # tưởng là thật. RootAgent.handle() đã tự xử lý gracefully: nếu intent
    # match "attendance"/"employee" nhưng registry.get(...) trả None, nó trả
    # về AgentResponse(success=False, error="Phân hệ '...' hiện chưa sẵn sàng.")
    # Khi 2 Agent kia xong (agents/attendance, agents/employee), chỉ cần thêm:
    #     from agents.attendance.attendance_agent import AttendanceAgent
    #     from agents.employee.employee_agent import EmployeeAgent
    #     registry.register(AttendanceAgent())
    #     registry.register(EmployeeAgent())

    return RootAgent(registry)


# Singleton dùng chung — Agent + tool dispatch map được tạo 1 lần lúc khởi động,
# không tạo lại mỗi request.
root_agent = build_root_agent()
