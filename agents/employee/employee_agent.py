"""Employee Agent implementation extending BaseAgent."""

import json
import os
import re
from typing import Any, Callable, Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from shared.abstractions.agent import AgentRequest, AgentResponse, BaseAgent
from mcp_servers.employee.tools import EmployeeTools
from .prompts import EMPLOYEE_AGENT_SYSTEM_PROMPT, INTENT_EXTRACTION_PROMPT


class EmployeeAgent(BaseAgent):
    """Domain Agent for the Employee / HR subsystem."""

    name: str = "employee"

    def __init__(
        self,
        mcp_client: Optional[Any] = None,
        tools: Optional[EmployeeTools] = None,
        openai_client: Optional[Any] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize EmployeeAgent."""
        self.mcp_client = mcp_client
        self.tools = tools or EmployeeTools()

        if openai_client is None and os.getenv("OPENAI_API_KEY"):
            try:
                from openai import OpenAI
                openai_client = OpenAI(
                    api_key=os.getenv("OPENAI_API_KEY"),
                    base_url=os.getenv("OPENAI_BASE_URL") or None,
                )
            except Exception:
                openai_client = None

        self.openai_client = openai_client
        self.model_name = model_name or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        self._tool_dispatch: Dict[str, Callable] = {
            "search_employees": self.tools.search_employees,
            "get_employee_profile": self.tools.get_employee_profile,
            "get_department_list": self.tools.get_department_list,
            "get_employee_department": self.tools.get_employee_department,
            "get_employee_summary": self.tools.get_employee_summary,
        }

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Handle an incoming user message routed from Root Agent."""
        message = (request.message or "").strip()
        if not message:
            return AgentResponse(
                success=False,
                error="Nội dung yêu cầu trống.",
                metadata={"source": "employee", "agent": self.name},
            )

        try:
            # 1. Parse intent & extract tool + parameters
            plan = self._extract_intent(message, request.context)

            # 2. Check if we need more clarification
            if plan.get("needs_more_info"):
                clarification = plan.get("clarification_message") or "Vui lòng cung cấp thêm thông tin để tôi hỗ trợ bạn tốt nhất."
                return AgentResponse(
                    success=True,
                    data={"response": clarification, "status": "needs_more_info"},
                    metadata={"source": "employee", "agent": self.name, "tool_used": None},
                )

            tool_name = plan.get("tool")
            params = plan.get("parameters", {})

            if not tool_name or tool_name not in self._tool_dispatch:
                return self._handle_general_query(message)

            # 3. Execute tool
            tool_result = self._execute_tool(tool_name, params)

            # 4. Synthesize natural language response
            synthesized_answer = self._synthesize_response(message, tool_name, params, tool_result)

            return AgentResponse(
                success=True,
                data={
                    "response": synthesized_answer,
                    "tool": tool_name,
                    "parameters": params,
                    "raw_tool_result": tool_result,
                },
                metadata={
                    "source": "employee",
                    "agent": self.name,
                    "tool_used": tool_name,
                    "parameters": params,
                },
            )

        except Exception as e:
            return AgentResponse(
                success=False,
                error=f"Đã có lỗi xảy ra khi xử lý yêu cầu nhân sự: {str(e)}",
                metadata={"source": "employee", "agent": self.name},
            )

    def _extract_intent(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract tool and parameters using LLM or rule-based fallback."""
        if self.openai_client:
            try:
                return self._extract_intent_with_llm(message, context)
            except Exception:
                pass
        return self._extract_intent_rule_based(message, context)

    def _extract_intent_with_llm(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call OpenAI LLM to parse intent and return structured JSON."""
        messages = [
            {"role": "system", "content": INTENT_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Yêu cầu người dùng: {message}"},
        ]
        if context:
            messages.insert(1, {"role": "system", "content": f"Ngữ cảnh phiên hội thoại: {json.dumps(context, ensure_ascii=False)}"})

        response = self.openai_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        content = response.choices[0].message.content
        return json.loads(content)

    def _extract_intent_rule_based(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fast offline rule-based intent parsing."""
        msg_lower = message.lower().strip()

        # Check for employee ID pattern (e.g. NV001, NV-001, NV 001)
        id_match = re.search(r"\b(nv[- ]?\d{3,4})\b", msg_lower, re.IGNORECASE)
        emp_id = None
        if id_match:
            emp_id = id_match.group(1).upper().replace(" ", "").replace("-", "")

        # 1. "Nhân viên A thuộc phòng ban nào?" / "thuộc phòng ban nào" / "ở phòng nào"
        if any(kw in msg_lower for kw in ["thuộc phòng ban", "ở phòng ban", "ở phòng nào", "thuộc khoa nào"]):
            # Extract employee name or identifier
            name_match = re.search(r"(?:nhân viên|thông tin|bạn)\s+([a-zA-Z0-9\s_à-ỹÀ-Ỹ]+?)(?:\s+thuộc|\s+ở|\s*\?|$)", message, re.IGNORECASE)
            identifier = emp_id or (name_match.group(1).strip() if name_match else "A")
            return {
                "tool": "get_employee_department",
                "parameters": {"identifier": identifier},
                "needs_more_info": False,
            }

        # 2. "Tìm thông tin nhân viên có mã ..." / "xem hồ sơ nhân viên"
        if emp_id and any(kw in msg_lower for kw in ["thông tin", "hồ sơ", "chi tiết", "mã", "tìm"]):
            return {
                "tool": "get_employee_profile",
                "parameters": {"employee_id": emp_id},
                "needs_more_info": False,
            }

        # If asking for profile without ID
        if any(kw in msg_lower for kw in ["xem hồ sơ", "chi tiết nhân viên"]) and not emp_id:
            # Check context
            if context and context.get("last_employee_id"):
                return {
                    "tool": "get_employee_profile",
                    "parameters": {"employee_id": context["last_employee_id"]},
                    "needs_more_info": False,
                }
            return {
                "tool": None,
                "parameters": {},
                "needs_more_info": True,
                "clarification_message": "Vui lòng cung cấp mã nhân viên (ví dụ: NV001) để tôi tra cứu hồ sơ chi tiết giúp bạn.",
            }

        # 3. Department list: "danh sách phòng ban", "công ty có những phòng ban nào", "các phòng ban"
        if any(kw in msg_lower for kw in ["danh sách phòng ban", "các phòng ban", "những phòng ban", "các khoa phòng"]):
            return {
                "tool": "get_department_list",
                "parameters": {},
                "needs_more_info": False,
            }

        # 4. Department member count / Summary: "Phòng ban Kỹ thuật có bao nhiêu nhân viên?", "Phòng ... có bao nhiêu người"
        dept_count_match = re.search(r"phòng\s+(?:ban\s+)?([a-zA-Z\s_à-ỹÀ-Ỹ]+?)\s+có\s+bao\s+nhiêu\s+(?:nhân viên|người)", msg_lower)
        if dept_count_match:
            dept_name = dept_count_match.group(1).strip()
            return {
                "tool": "get_employee_summary",
                "parameters": {"department_id": dept_name},
                "needs_more_info": False,
            }

        if any(kw in msg_lower for kw in ["thống kê nhân sự", "tổng số nhân viên", "có bao nhiêu nhân viên", "bao nhiêu người"]):
            return {
                "tool": "get_employee_summary",
                "parameters": {},
                "needs_more_info": False,
            }

        # 5. Search employees: "tìm nhân viên", "danh sách nhân viên"
        if any(kw in msg_lower for kw in ["tìm nhân viên", "danh sách nhân viên", "tra cứu nhân viên"]):
            return {
                "tool": "search_employees",
                "parameters": {"limit": 10},
                "needs_more_info": False,
            }

        # Fallback to search if keyword present
        return {
            "tool": "search_employees",
            "parameters": {"keyword": message, "limit": 5},
            "needs_more_info": False,
        }

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool via MCP Client or direct tool dispatch."""
        if self.mcp_client:
            try:
                return self.mcp_client.call_tool(tool_name, parameters)
            except Exception:
                pass

        handler = self._tool_dispatch.get(tool_name)
        if not handler:
            return {"success": False, "error": f"Tool '{tool_name}' không được hỗ trợ."}
        return handler(**parameters)

    def _synthesize_response(
        self,
        message: str,
        tool_name: str,
        parameters: Dict[str, Any],
        tool_result: Dict[str, Any],
    ) -> str:
        """Synthesize tool result into user-facing response."""
        if self.openai_client:
            try:
                return self._synthesize_response_with_llm(message, tool_name, parameters, tool_result)
            except Exception:
                pass
        return self._synthesize_response_template(tool_name, parameters, tool_result)

    def _synthesize_response_with_llm(
        self,
        message: str,
        tool_name: str,
        parameters: Dict[str, Any],
        tool_result: Dict[str, Any],
    ) -> str:
        """Call LLM to format natural response."""
        prompt = (
            f"{EMPLOYEE_AGENT_SYSTEM_PROMPT}\n\n"
            f"Câu hỏi của người dùng: {message}\n"
            f"Công cụ MCP đã gọi: {tool_name}\n"
            f"Tham số: {json.dumps(parameters, ensure_ascii=False)}\n"
            f"Kết quả trả về từ công cụ:\n{json.dumps(tool_result, ensure_ascii=False, indent=2)}\n\n"
            "Hãy trả lời câu hỏi của người dùng dựa trên kết quả trên một cách tự nhiên, chính xác, định dạng Markdown đẹp mắt."
        )
        response = self.openai_client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        return response.choices[0].message.content

    def _synthesize_response_template(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        tool_result: Dict[str, Any],
    ) -> str:
        """Fallback rule-based Markdown formatter."""
        if not tool_result.get("success", False):
            return f"❌ {tool_result.get('error', 'Không tìm thấy dữ liệu nhân sự tương ứng.')}"

        data = tool_result.get("data")
        if data is None:
            return "Không có dữ liệu trả về từ hệ thống nhân sự."

        if tool_name == "get_employee_department":
            emp_name = data.get("employee_name", "Nhân viên")
            dept_name = data.get("department_name", "Chưa rõ phòng ban")
            position = data.get("position", "")
            emp_id = data.get("employee_id", "")
            return (
                f"🏢 **Thông tin phòng ban của nhân viên:**\n\n"
                f"- **Họ và tên:** {emp_name} (`{emp_id}`)\n"
                f"- **Phòng ban:** **{dept_name}**\n"
                f"- **Chức vụ:** {position}\n"
            )

        if tool_name == "get_employee_profile":
            notes = f"\n- **Ghi chú:** {data.get('notes')}" if data.get("notes") else ""
            return (
                f"👤 **Hồ sơ chi tiết nhân viên [{data.get('id')} - {data.get('name')}]:**\n\n"
                f"- **Mã nhân viên:** `{data.get('id')}`\n"
                f"- **Họ và tên:** {data.get('name')}\n"
                f"- **Phòng ban:** {data.get('department_name')}\n"
                f"- **Chức vụ:** {data.get('position')}\n"
                f"- **Email:** {data.get('email')}\n"
                f"- **Số điện thoại:** {data.get('phone')}\n"
                f"- **Ngày vào làm:** {data.get('join_date')}\n"
                f"- **Trạng thái:** {data.get('status')}"
                f"{notes}"
            )

        if tool_name == "get_department_list":
            departments = data.get("departments", [])
            total = data.get("total_departments", len(departments))
            lines = [f"🏢 **Danh sách các phòng ban trong công ty ({total} phòng ban):**\n"]
            for d in departments:
                lines.append(
                    f"- **{d.get('name')}** (`{d.get('code')}`): "
                    f"Trưởng phòng: *{d.get('manager_name')}* | Nhân sự: **{d.get('member_count')}** người\n"
                    f"  *{d.get('description', '')}*"
                )
            return "\n".join(lines)

        if tool_name == "get_employee_summary":
            total = data.get("total_employees", 0)
            active = data.get("active_count", 0)
            by_dept = data.get("by_department", {})
            lines = [
                f"📊 **Báo cáo thống kê nhân sự:**\n",
                f"- **Tổng số nhân viên:** **{total}** người",
                f"- **Đang làm việc (active):** {active} người",
                f"- **Nghỉ phép / Khác:** {total - active} người\n",
                "**Phân bổ theo phòng ban:**",
            ]
            for dept, count in by_dept.items():
                lines.append(f"- **{dept}:** {count} nhân sự")
            return "\n".join(lines)

        if tool_name == "search_employees":
            employees = data.get("employees", [])
            total = data.get("total_found", len(employees))
            if not employees:
                return "Không tìm thấy nhân viên nào phù hợp với điều kiện tìm kiếm."
            lines = [f"📋 **Tìm thấy {total} nhân viên:**\n"]
            for e in employees:
                lines.append(
                    f"- **{e.get('name')}** (`{e.get('id')}`): {e.get('position')} - {e.get('department_name')}"
                )
            return "\n".join(lines)

        return f"Dữ liệu nhân sự:\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"

    def _handle_general_query(self, message: str) -> AgentResponse:
        """Handle general employee query."""
        reply = (
            "Chào bạn! Tôi là **Employee Agent** phụ trách phân hệ Nhân sự.\n\n"
            "Tôi có thể hỗ trợ bạn các tác vụ sau:\n"
            "- 👤 **Tra cứu hồ sơ nhân viên:** *'Tìm thông tin nhân viên có mã NV001'*\n"
            "- 🏢 **Tra cứu phòng ban của nhân viên:** *'Nhân viên A thuộc phòng ban nào?'*\n"
            "- 📋 **Danh sách phòng ban:** *'Công ty có những phòng ban nào?'*\n"
            "- 📊 **Thống kê nhân sự:** *'Phòng ban Kỹ thuật có bao nhiêu nhân viên?'*\n\n"
            "Bạn cần tra cứu thông tin gì?"
        )
        return AgentResponse(
            success=True,
            data={"response": reply},
            metadata={"source": "employee", "agent": self.name},
        )
