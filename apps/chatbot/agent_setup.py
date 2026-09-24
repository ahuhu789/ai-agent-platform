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
from agents.attendance.attendance_agent import AttendanceAgent
from agents.employee.employee_agent import EmployeeAgent


def build_root_agent() -> RootAgent:
    registry = AgentRegistry()

    # Đăng ký cả 3 Domain Agent thật vào AgentRegistry
    registry.register(HiringAgent())
    registry.register(AttendanceAgent())
    registry.register(EmployeeAgent())

    return RootAgent(registry)



# Singleton dùng chung — Agent + tool dispatch map được tạo 1 lần lúc khởi động,
# không tạo lại mỗi request.
root_agent = build_root_agent()
