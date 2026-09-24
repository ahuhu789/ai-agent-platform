"""Attendance Agent implementation extending BaseAgent."""

import json
import os
import re
import unicodedata
from datetime import datetime
from typing import Any, Callable, Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from shared.abstractions.agent import AgentRequest, AgentResponse, BaseAgent
from shared.abstractions.llm import BaseLLM, LLMRequest
from mcp_servers.attendance.tools import AttendanceTools
from .prompts import ATTENDANCE_AGENT_SYSTEM_PROMPT, INTENT_EXTRACTION_PROMPT


def strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp câu hỏi có dấu và không dấu."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", text)


class AttendanceAgent(BaseAgent):
    """Domain Agent for the Attendance / Chuyên cần subsystem."""

    name: str = "attendance"

    def __init__(
        self,
        mcp_client: Optional[Any] = None,
        tools: Optional[AttendanceTools] = None,
        llm: Optional[BaseLLM] = None,
        openai_client: Optional[Any] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize AttendanceAgent."""
        self.mcp_client = mcp_client
        self.tools = tools or AttendanceTools()
        self.llm = llm
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
                success=tool_result.get("success", False),
                data={
                    "response": synthesized_answer,
                    "tool": tool_name,
                    "parameters": params,
                    "raw_tool_result": tool_result,
                },
                error=tool_result.get("error"),
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
        if (self.llm and not getattr(self.llm, "is_mock", False)) or self.openai_client:
            try:
                return self._extract_intent_with_llm(message, context)
            except Exception:
                pass
        return self._extract_intent_rule_based(message, context)

    def _extract_intent_with_llm(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call LLM or OpenAI client to parse intent and return structured JSON."""
        messages = [
            {"role": "system", "content": INTENT_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Yêu cầu người dùng: {message}"},
        ]
        if context:
            messages.insert(1, {"role": "system", "content": f"Ngữ cảnh phiên hội thoại: {json.dumps(context, ensure_ascii=False)}"})

        if self.llm:
            req = LLMRequest(
                messages=messages,
                model=self.model_name,
                temperature=0.0,
            )
            resp = self.llm.generate(req)
            content = resp.content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```[a-zA-Z]*\n?", "", content)
                content = re.sub(r"\n?```$", "", content).strip()
            return json.loads(content)

        if self.openai_client:
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.0,
            )
            content = response.choices[0].message.content
            return json.loads(content)

        return self._extract_intent_rule_based(message, context)

    def _extract_intent_rule_based(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Fast offline rule-based intent parsing with diacritics stripping & aggregate query support."""
        msg_lower = message.lower().strip()
        msg_no_dia = strip_diacritics(msg_lower)

        def match_any(keywords):
            return any(k in msg_lower or k in msg_no_dia for k in keywords)

        # Check for aggregate cues: "ai", "ai đi trễ", "ai vắng mặt", "tất cả", "nhiều nhất", etc.
        has_aggregate_cue = match_any([
            "ai di tre", "ai đi trễ", "ai muon", "ai muộn", "ai vang", "ai vắng",
            "ai nghi", "ai nghỉ", "ai di lam", "ai đi làm",
            "nhieu nhat", "nhiều nhất", "it nhat", "ít nhất",
            "toan bo", "toàn bộ", "tat ca", "tất cả", "toan cong ty", "toàn công ty",
            "nhung ai", "những ai", "nhan vien nao", "nhân viên nào"
        ])
        is_who_question = match_any(["ai", "những ai", "ai đó"])

        # Extract Employee ID or Name
        id_match = re.search(r"\b(nv[- ]?\d{3,4})\b", msg_lower, re.IGNORECASE)
        emp_id = None
        if id_match:
            emp_id = id_match.group(1).upper().replace(" ", "").replace("-", "")

        # Look for "nhân viên A" or "nhân viên B"
        if not emp_id:
            name_match = re.search(r"nhân viên\s+([a-zA-Z0-9à-ỹÀ-Ỹ\s]+?)(?:\s+đi|\s+có|\s+vắng|\s+nghỉ|\s*\?|$)", msg_lower)
            if not name_match:
                name_match = re.search(r"nhan vien\s+([a-zA-Z0-9\s]+?)(?:\s+di|\s+co|\s+vang|\s+nghi|\s*\?|$)", msg_no_dia)
            if name_match:
                emp_name_part = name_match.group(1).strip().upper()
                if emp_name_part in ("A", "B", "C", "D", "E", "F", "G", "H", "I"):
                    emp_id = f"NV00{ord(emp_name_part) - ord('A') + 1}"
                elif emp_name_part == "K":
                    emp_id = "NV010"
                elif any(p in emp_name_part.lower() for p in ["này", "nay", "đó", "do", "ấy", "ay", "kia"]):
                    emp_id = None
                elif any(p in emp_name_part.lower() for p in ["nào", "nao", "ai"]):
                    emp_id = None
                else:
                    emp_id = name_match.group(1).strip()

        # If user asked an aggregate / who question and didn't specify a specific employee
        is_aggregate = (has_aggregate_cue or is_who_question) and (emp_id is None)

        # Fallback to context ONLY if not an aggregate query
        if not emp_id and not is_aggregate and context:
            emp_id = context.get("last_employee_id") or context.get("last_mentioned_employee_id")

        # Extract month & year from message if mentioned (e.g. "tháng 8", "tháng 9")
        month_match = re.search(r"tháng\s+(\d{1,2})", msg_lower) or re.search(r"thang\s+(\d{1,2})", msg_no_dia)
        year_match = re.search(r"năm\s+(\d{4})", msg_lower) or re.search(r"nam\s+(\d{4})", msg_no_dia)

        now = datetime.now()
        target_month = int(month_match.group(1)) if month_match else (now.month if now.year == 2026 and now.month in (8, 9) else 9)
        target_year = int(year_match.group(1)) if year_match else (now.year if now.year >= 2024 else 2026)

        # Extract dates YYYY-MM-DD
        dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", message)
        from_date = dates[0] if len(dates) > 0 else None
        to_date = dates[1] if len(dates) > 1 else None

        # 1. Late arrival query: "đi trễ", "đi muộn", "muộn giờ", "trễ bao nhiêu", "ai đi trễ", "trễ nhiều nhất"
        if match_any(["đi trễ", "di tre", "đi muộn", "di muon", "muộn giờ", "muon gio", "trễ bao nhiêu", "tre bao nhieu", "số lần trễ", "so lan tre", "trễ nhiều nhất", "tre nhieu nhat", "muộn nhiều nhất", "muon nhieu nhat", "ai trễ", "ai tre"]):
            target_emp = "ALL" if is_aggregate else (emp_id or "NV001")
            return {
                "tool": "get_late_arrival_summary",
                "parameters": {"employee_id": target_emp, "month": target_month, "year": target_year},
                "needs_more_info": False,
            }

        # 2. Absence / Leave query: "vắng mặt", "nghỉ phép", "nghỉ việc", "ai vắng", "vắng nhiều nhất"
        if match_any(["vắng mặt", "vang mat", "nghỉ phép", "nghi phep", "nghỉ không phép", "nghi khong phep", "vắng", "vang", "nghỉ việc", "nghi viec", "vắng nhiều nhất", "vang nhieu nhat", "ai vắng", "ai vang", "ai nghỉ", "ai nghi"]):
            target_emp = "ALL" if is_aggregate else (emp_id or "NV001")
            return {
                "tool": "get_absence_summary",
                "parameters": {"employee_id": target_emp, "month": target_month, "year": target_year},
                "needs_more_info": False,
            }

        # 3. Attendance history: "lịch sử chuyên cần", "lịch sử chấm công", "từ ngày ... đến ngày ..."
        if match_any(["lịch sử", "lich su", "chấm công từ", "cham cong tu", "từ ngày", "tu ngay", "chi tiết chấm công", "chi tiet cham cong"]):
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
        if match_any(["đi làm", "di lam", "bao nhiêu ngày", "bao nhieu ngay", "ngày công", "ngay cong", "tháng này", "thang nay", "tháng 8", "thang 8", "tháng 9", "thang 9", "số ngày làm", "so ngay lam", "chuyên cần tháng", "chuyen can thang"]):
            if is_aggregate:
                return {
                    "tool": "get_attendance_statistics",
                    "parameters": {"month": target_month, "year": target_year},
                    "needs_more_info": False,
                }
            target_emp = emp_id or "NV001"
            return {
                "tool": "get_monthly_attendance",
                "parameters": {"employee_id": target_emp, "month": target_month, "year": target_year},
                "needs_more_info": False,
            }

        # 5. Overall statistics: "thống kê chuyên cần", "tỷ lệ đi làm", "tổng hợp chuyên cần", "toàn công ty"
        if match_any(["thống kê", "thong ke", "tỷ lệ chuyên cần", "ty le chuyen can", "tổng hợp", "tong hop", "toàn công ty", "toan cong ty", "báo cáo chuyên cần", "bao cao chuyen can"]):
            return {
                "tool": "get_attendance_statistics",
                "parameters": {"month": target_month, "year": target_year},
                "needs_more_info": False,
            }

        # If has emp_id, default to monthly attendance
        if emp_id:
            return {
                "tool": "get_monthly_attendance",
                "parameters": {"employee_id": emp_id, "month": target_month, "year": target_year},
                "needs_more_info": False,
            }

        return {
            "tool": "get_attendance_statistics",
            "parameters": {"month": target_month, "year": target_year},
            "needs_more_info": False,
        }

    def _execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool via MCP Client or direct tool dispatch."""
        if self.mcp_client:
            try:
                if hasattr(self.mcp_client, "call_tool_sync"):
                    res = self.mcp_client.call_tool_sync(self.name, tool_name, parameters)
                    if hasattr(res, "success"):
                        return {"success": res.success, "data": res.data, "error": res.error, "metadata": getattr(res, "metadata", {})}
                    return res
                return self.mcp_client.call_tool(self.name, tool_name, parameters)
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
        if (self.llm and not getattr(self.llm, "is_mock", False)) or self.openai_client:
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
        """Call LLM or OpenAI client to format natural response."""
        system_prompt = (
            "Bạn là Trợ lý Chuyên cần (Attendance Agent) thông minh, chuyên nghiệp của hệ thống FME.\n"
            "Nhiệm vụ: Dựa vào DỮ LIỆU THỰC TẾ từ Tool vừa gọi để trả lời người dùng một cách chính xác, tự nhiên bằng tiếng Việt.\n"
            "QUY TẮC ĐỊNH DẠNG BẮT BUỘC:\n"
            "- Với chi tiết 1 cá nhân (như số ngày đi làm, thống kê đi trễ cá nhân): Trình bày dạng chi tiết / card rõ ràng với các mục bullet points. BẮT BUỘC ghi rõ Mã nhân viên (ví dụ: `NV001`), Họ và tên, Số ngày làm việc hoặc số lần trễ. KHÔNG ép thành bảng 1 dòng.\n"
            "- Khi kết quả là danh sách từ 2 bản ghi trở lên (lịch sử chuyên cần nhiều ngày, bảng xếp hạng đi trễ/vắng mặt nhiều nhân viên...): BẮT BUỘC dùng bảng Markdown (Markdown Table) chuẩn. Cột đầu tiên là STT, tiếp đến Mã NV / Ngày, rồi đến các thông tin.\n"
            "- Bảng có tiêu đề ngắn gọn (dùng ###). Cột số liệu (STT, số lần trễ, số phút, ngày nghỉ) phải căn phải (|---:|), các cột khác căn trái (|---|).\n"
            "- Sau bảng có MỘT dòng tổng kết ngắn gọn (ví dụ: **Tổng số:** X bản ghi.), KHÔNG lặp lại toàn bộ dữ liệu bên dưới.\n"
            "- Tuyệt đối KHÔNG escape ký tự gạch đứng | thành \\| trong bảng.\n"
            "- Tuyệt đối KHÔNG escape ký tự @ trong email thành \\@.\n"
            "- Không tự thêm quá nhiều emoji hoặc định dạng rườm rà không cần thiết.\n"
            "- Tuyệt đối không bịa đặt dữ liệu ngoài thông tin do Tool cung cấp."
        )
        prompt = (
            f"{system_prompt}\n\n"
            f"Câu hỏi của người dùng: {message}\n"
            f"Công cụ MCP đã gọi: {tool_name}\n"
            f"Tham số: {json.dumps(parameters, ensure_ascii=False)}\n"
            f"Kết quả trả về từ công cụ:\n{json.dumps(tool_result, ensure_ascii=False, indent=2)}\n\n"
            "Hãy trả lời câu hỏi của người dùng dựa trên kết quả trên một cách tự nhiên, rõ ràng, định dạng Markdown đẹp mắt."
        )

        if self.llm and not getattr(self.llm, "is_mock", False):
            req = LLMRequest(
                messages=[{"role": "user", "content": prompt}],
                model=self.model_name,
                temperature=0.2,
            )
            resp = self.llm.generate(req)
            if resp.content and resp.content.strip():
                return resp.content.strip()

        if self.openai_client:
            response = self.openai_client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            return response.choices[0].message.content

        return self._synthesize_response_template(tool_name, parameters, tool_result)

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
                f"### Thông tin chuyên cần tháng {month}/{year}\n\n"
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

            # Trường hợp truy vấn tập thể / toàn công ty (VD: "Ai đi trễ nhiều nhất?")
            if emp_id == "ALL" or emp_name in ("Toàn bộ nhân viên", "Tất cả nhân viên"):
                if not details:
                    return f"🎉 Trong tháng {month}/{year}, toàn công ty không có nhân viên nào đi trễ."

                from collections import defaultdict
                emp_stats = defaultdict(lambda: {"name": "", "count": 0, "minutes": 0, "dates": []})
                for d in details:
                    eid = d.get("employee_id", "NV")
                    ename = d.get("employee_name", eid)
                    emp_stats[eid]["name"] = ename
                    emp_stats[eid]["count"] += 1
                    emp_stats[eid]["minutes"] += d.get("late_minutes", 0)
                    emp_stats[eid]["dates"].append(f"{d.get('date')} ({d.get('late_minutes')}p)")

                sorted_emps = sorted(emp_stats.items(), key=lambda x: (x[1]["count"], x[1]["minutes"]), reverse=True)
                max_count = sorted_emps[0][1]["count"] if sorted_emps else 0
                top_late_names = [f"**{info['name']}** (`{eid}` - {info['count']} lần)" for eid, info in sorted_emps if info["count"] == max_count]

                lines = [
                    f"### Thống kê nhân viên đi trễ tháng {month}/{year}\n",
                    f"- **Nhân viên đi trễ nhiều nhất:** {', '.join(top_late_names)}",
                    f"- **Tổng số lượt đi trễ toàn công ty:** **{late_count} lượt** (Tổng cộng: {total_mins} phút)\n",
                    "**Bảng xếp hạng đi trễ chi tiết:**\n",
                    "| STT | Mã NV | Họ và tên | Số lần trễ | Tổng phút trễ | Chi tiết ngày trễ |",
                    "|---:|---|---|---:|---:|---|",
                ]
                for idx, (eid, info) in enumerate(sorted_emps, 1):
                    date_str = ", ".join(info["dates"])
                    lines.append(f"| {idx} | `{eid}` | **{info['name']}** | {info['count']} lần | {info['minutes']} phút | {date_str} |")

                lines.append(f"\n**Tổng số:** {len(sorted_emps)} nhân viên đi trễ.")
                return "\n".join(lines)

            # Trường hợp cá nhân 1 nhân viên
            lines = [
                f"### Thống kê đi trễ tháng {month}/{year}\n\n"
                f"- **Nhân viên:** **{emp_name}** (`{emp_id}`)\n"
                f"- **Số lần đi trễ:** **{late_count} lần**\n"
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
                f"### Lịch sử chuyên cần nhân viên `{emp_id}` ({total} bản ghi)\n",
                "| STT | Ngày | Giờ vào | Giờ ra | Trạng thái | Ghi chú |",
                "|---:|---|---|---|---|---|",
            ]
            for idx, r in enumerate(records, 1):
                status_icon = "Đúng giờ" if r.get("status") == "on_time" else ("Trễ" if r.get("status") == "late" else "Vắng")
                c_in = r.get("check_in") or "-"
                c_out = r.get("check_out") or "-"
                lines.append(f"| {idx} | {r.get('date')} | {c_in} | {c_out} | {status_icon} | {r.get('notes') or ''} |")
            lines.append(f"\n**Tổng số:** {total} bản ghi.")
            return "\n".join(lines)

        if tool_name == "get_absence_summary":
            emp_name = data.get("employee_name", "Nhân viên")
            emp_id = data.get("employee_id", "")
            month = data.get("month", 9)
            year = data.get("year", 2026)
            absent_days = data.get("absent_days", 0)
            leave_perm = data.get("leave_with_permission", 0)
            details = data.get("details", [])

            # Trường hợp truy vấn tập thể / toàn công ty (VD: "Ai vắng mặt nhiều nhất?")
            if emp_id == "ALL" or emp_name in ("Toàn bộ nhân viên", "Tất cả nhân viên"):
                if not details:
                    return f"🎉 Trong tháng {month}/{year}, toàn công ty không có nhân viên nào vắng mặt hay nghỉ phép."

                from collections import defaultdict
                emp_absent = defaultdict(lambda: {"name": "", "count": 0, "reasons": []})
                for d in details:
                    eid = d.get("employee_id", "NV")
                    ename = d.get("employee_name", eid)
                    emp_absent[eid]["name"] = ename
                    emp_absent[eid]["count"] += 1
                    emp_absent[eid]["reasons"].append(f"{d.get('date')} (*{d.get('notes', 'Nghỉ phép')}*)")

                sorted_absent = sorted(emp_absent.items(), key=lambda x: x[1]["count"], reverse=True)
                max_absent = sorted_absent[0][1]["count"] if sorted_absent else 0
                top_absent_names = [f"**{info['name']}** (`{eid}` - {info['count']} ngày)" for eid, info in sorted_absent if info["count"] == max_absent]

                lines = [
                    f"### Báo cáo nhân viên vắng mặt / nghỉ phép tháng {month}/{year}\n",
                    f"- **Nhân viên vắng mặt nhiều nhất:** {', '.join(top_absent_names)}",
                    f"- **Tổng số ngày nghỉ toàn công ty:** **{absent_days} ngày**\n",
                    "**Danh sách chi tiết:**\n",
                    "| STT | Mã NV | Họ và tên | Số ngày nghỉ | Chi tiết ngày nghỉ |",
                    "|---:|---|---|---:|---|",
                ]
                for idx, (eid, info) in enumerate(sorted_absent, 1):
                    reasons_str = "; ".join(info["reasons"])
                    lines.append(f"| {idx} | `{eid}` | **{info['name']}** | {info['count']} ngày | {reasons_str} |")

                lines.append(f"\n**Tổng số:** {len(sorted_absent)} nhân viên có ngày nghỉ.")
                return "\n".join(lines)

            # Trường hợp cá nhân 1 nhân viên
            lines = [
                f"### Báo cáo vắng mặt & nghỉ phép\n\n"
                f"- **Nhân viên:** **{emp_name}** (`{emp_id}`)\n"
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
