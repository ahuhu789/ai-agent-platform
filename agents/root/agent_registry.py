from shared.abstractions.agent import BaseAgent


class AgentRegistry:
    """Nơi đăng ký và tra cứu Agent theo tên phân hệ (Registry pattern).

    Root Agent không cần biết Hiring/Attendance/Employee Agent được tạo ra
    thế nào - chỉ cần gọi registry.get("hiring") là lấy được Agent đúng.
    Nhờ vậy, thay Mock Agent bằng Agent thật chỉ cần đổi ở nơi gọi register(),
    không phải sửa RootAgent.
    """

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent):
        if agent.name in self._agents:
            # Không chặn hẳn (có thể là cố ý thay Mock bằng Agent thật),
            # nhưng cảnh báo để tránh trường hợp đăng ký nhầm 2 Agent cùng tên
            # mà không hay - lỗi kiểu này rất khó nhận ra nếu không có cảnh báo.
            print(f"[AgentRegistry] Cảnh báo: '{agent.name}' đã được đăng ký trước đó, đang ghi đè.")
        self._agents[agent.name] = agent

    def get(self, name: str):
        return self._agents.get(name)

    def list_agents(self) -> list[str]:
        return list(self._agents.keys())