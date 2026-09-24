"""Attendance Agent implementation extending BaseAgent."""

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
from mcp_servers.attendance.tools import AttendanceTools
from .prompts import ATTENDANCE_AGENT_SYSTEM_PROMPT, INTENT_EXTRACTION_PROMPT


class AttendanceAgent(BaseAgent):
    """Domain Agent for the Attendance / Chuyên cần subsystem."""

    name: str = "attendance"

    def __init__(
        self,
        mcp_client: Optional[Any] = None,
        tools: Optional[AttendanceTools] = None,
        openai_client: Optional[Any] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize AttendanceAgent."""
        self.mcp_client = mcp_client
        self.tools = tools or AttendanceTools()

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
            "get_monthly_attendance": self.tools.get_monthly_attendance,
            "get_late_arrival_summary": self.tools.get_late_arrival_summary,
            "get_attendance_history": self.tools.get_attendance_history,
            "get_absence_summary": self.tools.get_absence_summary,
            "get_attendance_statistics": self.tools.get_attendance_statistics,
        }

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Handle an incoming user message routed from Root Agent."""
        message = (request.message or "").strip()
        if not message:
            return AgentResponse(
                success=False,
                error="Nội dung yêu cầu trống.",
                metadata={"source": "attendance", "agent": self.name},
            )

        try:
            # 1. Parse intent & extract tool + parameters
            plan = self._extract_intent(message, request.context)

            # 2. Check if we need more clarification
            if plan.get("needs_more_info"):
                clarification = plan.get("clarification_message") or "Vui lòng cung cấp thêm mã nhân viên để tôi tra cứu chuyên cần."
                return AgentResponse(
                    success=True,
                    data={"response": clarification, "status": "needs_more_info"},
                    metadata={"source": "attendance", "agent": self.name, "tool_used": None},
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
                    "source": "attendance",
                    "agent": self.name,
                    "tool_used": tool_name,
                    "parameters": params,
                },
            )

        except Exception as e:
            return AgentResponse(
                success=False,
                error=f"Đã có lỗi xảy ra khi xử lý yêu cầu chuyên cần: {str(e)}",
                metadata={"source": "attendance", "agent": self.name},
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

        # Extract Employee ID or Name
        id_match = re.search(r"\b(nv[- ]?\d{3,4})\b", msg_lower, re.IGNORECASE)
        emp_id = None
        if id_match:
            emp_id = id_match.group(1).upper().replace(" ", "").replace("-", "")

        # Look for "nhân viên A" or "nhân viên B"
        if not emp_id:
            name_match = re.search(r"nhân viên\s+([a-zA-Z0-9à-ỹÀ-Ỹ\s]+?)(?:\s+đi|\s+có|\s+vắng|\s+nghỉ|\s*\?|$)", msg_lower)
            if name_match:
                emp_name_part = name_match.group(1).strip().upper()
                if emp_name_part in ("A", "B", "C", "D", "E", "F", "G", "H", "I"):
                    emp_id = f"NV00{ord(emp_name_part) - ord('A') + 1}"
                elif emp_name_part == "K":
                    emp_id = "NV010"
                elif not any(p in emp_name_part.lower() for p in ["này", "đó", "ấy", "kia"]):
                    emp_id = name_match.group(1).strip()

        # Fallback to context
        if not emp_id and context:
            emp_id = context.get("last_employee_id") or context.get("last_mentioned_employee_id")

        # Extract month & year from message if mentioned (e.g. "tháng 8", "tháng 9")
        month_match = re.search(r"tháng\s+(\d{1,2})", msg_lower)
        target_month = int(month_match.group(1)) if month_match else 9
        year_match = re.search(r"năm\s+(\d{4})", msg_lower)
        target_year = int(year_match.group(1)) if year_match else 2026

        # Extract dates YYYY-MM-DD
        dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", message)
        from_date = dates[0] if len(dates) > 0 else None
        to_date = dates[1] if len(dates) > 1 else None

        # 1. Late arrival query: "đi trễ bao nhiêu lần", "đi muộn", "số lần trễ"
        if any(kw in msg_lower for kw in ["đi trễ", "di tre", "đi muộn", "muộn giờ", "trễ bao nhiêu"]):
            target_emp = emp_id or "NV001"
            return {
                "tool": "get_late_arrival_summary",
                "parameters": {"employee_id": target_emp, "month": target_month, "year": target_year},
                "needs_more_info": False,
            }

        # 2. Absence / Leave query: "vắng mặt", "nghỉ phép", "nghỉ việc"
        if any(kw in msg_lower for kw in ["vắng mặt", "vang mat", "nghỉ phép", "nghi phep", "nghỉ không phép"]):
            target_emp = emp_id or "NV001"
            return {
                "tool": "get_absence_summary",
                "parameters": {"employee_id": target_emp, "month": target_month, "year": target_year},
                "needs_more_info": False,
            }

        # 3. Attendance history: "lịch sử chuyên cần", "lịch sử chấm công", "từ ngày ... đến ngày ..."
        if any(kw in msg_lower for kw in ["lịch sử", "lich su", "chấm công từ", "từ ngày"]):
            target_emp = emp_id or "NV001"
            return {
                "tool": "get_attendance_history",
                "parameters": {
                    "employee_id": target_emp,
                    "from_date": from_date or f"{target_year:04d}-{target_month:02d}-01",
                    "to_date": to_date or f"{target_year:04d}-{target_month:02d}-24",
                },
                "needs_more_info": False,
            }

        # 4. Monthly attendance / Days worked: "đi làm bao nhiêu ngày", "tháng này đi làm", "chuyên cần tháng"
        if any(kw in msg_lower for kw in ["đi làm", "di lam", "bao nhiêu ngày", "tháng này", "tháng 8", "tháng 9"]):
            target_emp = emp_id or "NV001"
            return {
                "tool": "get_monthly_attendance",
                "parameters": {"employee_id": target_emp, "month": target_month, "year": target_year},
                "needs_more_info": False,
            }

        # 5. Overall statistics: "thống kê chuyên cần", "tỷ lệ đi làm", "tổng hợp chuyên cần"
        if any(kw in msg_lower for kw in ["thống kê", "tỷ lệ chuyên cần", "tổng hợp"]):
            return {
                "tool": "get_attendance_statistics",
                "parameters": {"month": 9, "year": 2026},
                "needs_more_info": False,
            }

        # If has emp_id, default to monthly attendance
        if emp_id:
            return {
                "tool": "get_monthly_attendance",
                "parameters": {"employee_id": emp_id, "month": 9, "year": 2026},
                "needs_more_info": False,
            }

        return {
            "tool": "get_attendance_statistics",
            "parameters": {"month": 9, "year": 2026},
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
            f"{ATTENDANCE_AGENT_SYSTEM_PROMPT}\n\n"
            f"Câu hỏi của người dùng: {message}\n"
            f"Công cụ MCP đã gọi: {tool_name}\n"
            f"Tham số: {json.dumps(parameters, ensure_ascii=False)}\n"
            f"Kết quả trả về từ công cụ:\n{json.dumps(tool_result, ensure_ascii=False, indent=2)}\n\n"
            "Hãy trả lời câu hỏi của người dùng dựa trên kết quả trên một cách tự nhiên, rõ ràng, định dạng Markdown đẹp mắt."
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
            return f"❌ {tool_result.get('error', 'Không tìm thấy dữ liệu chuyên cần tương ứng.')}"

        data = tool_result.get("data")
        if data is None:
            return "Không có dữ liệu trả về từ hệ thống chuyên cần."

        if tool_name == "get_monthly_attendance":
            emp_name = data.get("employee_name", "Nhân viên")
            emp_id = data.get("employee_id", "")
            month = data.get("month", 9)
            year = data.get("year", 2026)
            days_worked = data.get("actual_working_days", 0)
            total_days = data.get("total_working_days", 0)
            late = data.get("late_count", 0)
            absent = data.get("absent_count", 0)
            rate = data.get("attendance_rate", 100.0)

            return (
                f"📅 **Thông tin chuyên cần tháng {month}/{year}:**\n\n"
                f"- **Nhân viên:** **{emp_name}** (`{emp_id}`)\n"
                f"- **Số ngày đi làm thực tế:** **{days_worked}** / {total_days} ngày\n"
                f"- **Số lần đi trễ:** {late} lần\n"
                f"- **Số ngày vắng mặt:** {absent} ngày\n"
                f"- **Tỷ lệ chuyên cần:** **{rate}%**\n\n"
                f"*(Tháng này nhân viên {emp_name} đã đi làm **{days_worked} ngày**)*"
            )

        if tool_name == "get_late_arrival_summary":
            emp_name = data.get("employee_name", "Nhân viên")
            emp_id = data.get("employee_id", "")
            month = data.get("month", 9)
            year = data.get("year", 2026)
            late_count = data.get("late_count", 0)
            total_mins = data.get("total_late_minutes", 0)
            details = data.get("details", [])

            lines = [
                f"⏰ **Thống kê đi trễ tháng {month}/{year}:**\n",
                f"- **Nhân viên:** **{emp_name}** (`{emp_id}`)",
                f"- **Số lần đi trễ:** **{late_count} lần**",
                f"- **Tổng thời gian trễ:** {total_mins} phút\n",
            ]
            if details:
                lines.append("**Chi tiết các lần đi trễ:**")
                for d in details:
                    lines.append(f"- Ngày `{d.get('date')}`: Vào lúc `{d.get('check_in')}` (Trễ {d.get('late_minutes')} phút - *{d.get('notes', '')}*)")
            else:
                lines.append("🎉 *Nhân viên không có lần đi trễ nào trong tháng.*")

            return "\n".join(lines)

        if tool_name == "get_attendance_history":
            records = data.get("records", [])
            total = data.get("total_records", len(records))
            emp_id = data.get("employee_id", "")
            if not records:
                return f"Không có lịch sử chấm công cho nhân viên `{emp_id}` trong khoảng thời gian đã chọn."

            lines = [
                f"📋 **Lịch sử chuyên cần nhân viên `{emp_id}` ({total} bản ghi):**\n",
                "| Ngày | Giờ vào | Giờ ra | Trạng thái | Ghi chú |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ]
            for r in records:
                status_icon = "✅ Đúng giờ" if r.get("status") == "on_time" else ("⏰ Trễ" if r.get("status") == "late" else "❌ Vắng")
                c_in = r.get("check_in") or "-"
                c_out = r.get("check_out") or "-"
                lines.append(f"| {r.get('date')} | {c_in} | {c_out} | {status_icon} | {r.get('notes') or ''} |")
            return "\n".join(lines)

        if tool_name == "get_absence_summary":
            emp_name = data.get("employee_name", "Nhân viên")
            emp_id = data.get("employee_id", "")
            absent_days = data.get("absent_days", 0)
            leave_perm = data.get("leave_with_permission", 0)
            details = data.get("details", [])

            lines = [
                f"🏖️ **Báo cáo vắng mặt & nghỉ phép:**\n",
                f"- **Nhân viên:** **{emp_name}** (`{emp_id}`)",
                f"- **Số ngày nghỉ phép:** **{absent_days} ngày** (Có phép: {leave_perm} ngày)",
            ]
            if details:
                lines.append("\n**Chi tiết:**")
                for d in details:
                    lines.append(f"- Ngày `{d.get('date')}`: {d.get('notes', 'Nghỉ phép')}")
            return "\n".join(lines)

        if tool_name == "get_attendance_statistics":
            total = data.get("total_employees", 0)
            rate = data.get("average_attendance_rate", 0)
            late = data.get("total_late_incidents", 0)
            lines = [
                f"📊 **Báo cáo chuyên cần tổng hợp tháng {data.get('month')}/{data.get('year')}:**\n",
                f"- **Quy mô nhân sự:** {total} người",
                f"- **Tỷ lệ chuyên cần bình quân:** **{rate}%**",
                f"- **Tổng số lượt đi trễ:** {late} lượt",
            ]
            return "\n".join(lines)

        return f"Dữ liệu chuyên cần:\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```"

    def _handle_general_query(self, message: str) -> AgentResponse:
        """Handle general attendance query."""
        reply = (
            "Chào bạn! Tôi là **Attendance Agent** phụ trách phân hệ Chuyên cần / Chấm công.\n\n"
            "Tôi có thể hỗ trợ bạn các tác vụ sau:\n"
            "- 📅 **Số ngày đi làm:** *'Tháng này nhân viên A đi làm bao nhiêu ngày?'*\n"
            "- ⏰ **Số lần đi trễ:** *'Nhân viên A đi trễ bao nhiêu lần?'*\n"
            "- 📋 **Lịch sử chuyên cần:** *'Cho tôi lịch sử chuyên cần từ ngày 2026-09-01 đến ngày 2026-09-24'*\n"
            "- 🏖️ **Vắng mặt / Nghỉ phép:** *'Nhân viên NV001 có vắng mặt ngày nào không?'*\n\n"
            "Bạn muốn tra cứu thông tin chuyên cần nào?"
        )
        return AgentResponse(
            success=True,
            data={"response": reply},
            metadata={"source": "attendance", "agent": self.name},
        )
