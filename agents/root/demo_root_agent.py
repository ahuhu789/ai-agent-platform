"""
demo_root_agent.py
-------------------
File demo de CHAY TRONG TERMINAL khi quay video gioi thieu Root Agent.
Khong phai file test tu dong (khong dung pytest) - chi de in ket qua ra
man hinh cho truc quan luc quay demo.

Cach chay (dung vi tri THU MUC GOC du an D:\\ai-agent):
    1. Neu dang o agents/root thi lui ra: cd ../..
    2. Chay bang lenh:
       python -m agents.root.demo_root_agent
"""

import time

from shared.abstractions.agent import AgentRequest
from agents.root.agent_registry import AgentRegistry
from agents.root.root_agent import RootAgent
from agents.root.mock_agents import MockHiringAgent, MockAttendanceAgent, MockEmployeeAgent


# ============================================================
# HAM TIEN ICH DE IN DEP RA TERMINAL (cho video de nhin)
# ============================================================
def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def ask(root_agent: RootAgent, question: str):
    print(f"\n>>> Cau hoi: \"{question}\"")
    time.sleep(0.5)  # do tre nho de video khong bi "nhay" qua nhanh

    request = AgentRequest(message=question)
    response = root_agent.handle(request)

    intent = response.metadata.get("intent")
    print(f"    -> Phan he duoc chon : {intent if intent else 'KHONG XAC DINH (fallback)'}")
    if response.success:
        print(f"    -> Ket qua tra ve    : {response.data}")
    else:
        print(f"    -> Phan hoi          : {response.error}")

    time.sleep(1.5)  # giu man hinh de nguoi xem kip doc


# ============================================================
# KHOI TAO REGISTRY + MOCK AGENT CHO 3 PHAN HE
# ============================================================
print_header("KHOI TAO ROOT AGENT VA AGENT REGISTRY")

registry = AgentRegistry()
registry.register(MockHiringAgent())
registry.register(MockAttendanceAgent())
registry.register(MockEmployeeAgent())

print("Da dang ky 3 Agent vao Registry: hiring, attendance, employee")
time.sleep(1)

root_agent = RootAgent(registry)


# ============================================================
# DEMO 4 CAU HOI: 3 phan he + 1 cau fallback
# ============================================================
print_header("DEMO ROUTING - 3 NHOM INTENT")

ask(root_agent, "Có bao nhiêu ứng viên đang chờ phỏng vấn?")        # -> hiring
ask(root_agent, "Tháng này nhân viên A đi làm bao nhiêu ngày?")     # -> attendance
ask(root_agent, "Nhân viên A thuộc phòng ban nào?")                 # -> employee

print_header("DEMO FALLBACK - CAU HOI KHONG XAC DINH DUOC PHAN HE")

ask(root_agent, "Hôm nay thời tiết thế nào?")                       # -> fallback

print_header("KET THUC DEMO ROOT AGENT")
