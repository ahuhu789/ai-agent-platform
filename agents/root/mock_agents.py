from shared.abstractions.agent import BaseAgent, AgentRequest, AgentResponse


class MockHiringAgent(BaseAgent):
    name = "hiring"

    def handle(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            success=True,
            data={"candidates_waiting_interview": 5},
            metadata={"source": "hiring", "mock": True},
        )


class MockAttendanceAgent(BaseAgent):
    name = "attendance"

    def handle(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            success=True,
            data={"days_worked_this_month": 18},
            metadata={"source": "attendance", "mock": True},
        )


class MockEmployeeAgent(BaseAgent):
    name = "employee"

    def handle(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            success=True,
            data={"employee_name": "Nguyễn Văn A", "department": "Kỹ thuật"},
            metadata={"source": "employee", "mock": True},
        )