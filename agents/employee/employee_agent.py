"""Employee Agent implementation extending BaseAgent."""

import json
import os
import re
import unicodedata
from typing import Any, Callable, Dict, Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from shared.abstractions.agent import AgentRequest, AgentResponse, BaseAgent
from shared.abstractions.llm import BaseLLM, LLMRequest
from mcp_servers.employee.tools import EmployeeTools
from .prompts import EMPLOYEE_AGENT_SYSTEM_PROMPT, INTENT_EXTRACTION_PROMPT


def strip_diacritics(text: str) -> str:
    """Bỏ dấu tiếng Việt để so khớp câu hỏi có dấu và không dấu."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d").replace("Đ", "D")
    return unicodedata.normalize("NFC", text)


class EmployeeAgent(BaseAgent):
    """Domain Agent for the Employee / HR subsystem."""

    name: str = "employee"

    def __init__(
        self,
        mcp_client: Optional[Any] = None,
        tools: Optional[EmployeeTools] = None,
        llm: Optional[BaseLLM] = None,
        openai_client: Optional[Any] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize EmployeeAgent."""
        self.mcp_client = mcp_client
        self.tools = tools or EmployeeTools()
        self.llm = llm
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
                success=tool_result.get("success", False),
                data={
                    "response": synthesized_answer,
                    "tool": tool_name,
                    "parameters": params,
                    "raw_tool_result": tool_result,
                },
                error=tool_result.get("error"),
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
        """Fast offline rule-based intent parsing with diacritics stripping."""
        msg_lower = message.lower().strip()
        msg_no_dia = strip_diacritics(msg_lower)

        def match_any(keywords):
            return any(k in msg_lower or k in msg_no_dia for k in keywords)

        # Check for employee ID pattern (e.g. NV001, NV-001, NV 001)
        id_match = re.search(r"\b(nv[- ]?\d{3,4})\b", msg_lower, re.IGNORECASE)
        emp_id = None
        if id_match:
            emp_id = id_match.group(1).upper().replace(" ", "").replace("-", "")

        # Look for "nhân viên A" or "nhân viên B" or full name
        if not emp_id:
            letter_match = re.search(r"(?:nhân viên|nhan vien)\s+([A-Za-z])\b", message, re.IGNORECASE)
            if letter_match:
                emp_name_part = letter_match.group(1).upper()
                if emp_name_part in ("A", "B", "C", "D", "E", "F", "G", "H", "I"):
                    emp_id = f"NV00{ord(emp_name_part) - ord('A') + 1}"
                elif emp_name_part == "K":
                    emp_id = "NV010"
                else:
                    emp_id = emp_name_part
            else:
                name_match = re.search(r"(?:nhân viên|nhan vien)\s+([a-zA-Z0-9à-ỹÀ-Ỹ\s]+?)(?:\s+thuộc|\s+thuoc|\s+ở|\s+o|\s+có|\s+co|\s+phòng|\s+phong|\s+ban|\s*\?|$)", message, re.IGNORECASE)
                if name_match:
                    emp_name_part = name_match.group(1).strip()
                    if any(p in emp_name_part.lower() for p in ["này", "nay", "đó", "do", "ấy", "ay", "kia", "nào", "nao", "ai"]):
                        emp_id = None
                    else:
                        emp_id = emp_name_part

        # Recover from context if available
        ctx_emp_id = None
        ctx_emp_name = None
        if context:
            ctx_emp_id = context.get("last_employee_id") or context.get("last_mentioned_employee_id")
            ctx_emp_name = context.get("last_employee_name") or context.get("last_mentioned_employee_name")

        emp_id = emp_id or ctx_emp_id

        # 1. Department list: "danh sách phòng ban", "công ty có những phòng ban nào", "các phòng ban"
        # Check this BEFORE get_employee_department so "Công ty có những phòng ban nào?" doesn't get hijacked
        if match_any(["danh sách phòng ban", "danh sach phong ban", "các phòng ban", "cac phong ban", "những phòng ban", "nhung phong ban", "các khoa phòng", "cac khoa phong", "công ty có những phòng ban nào", "co nhung phong ban nao"]):
            return {
                "tool": "get_department_list",
                "parameters": {},
                "needs_more_info": False,
            }

        # 2. "Nhân viên A thuộc phòng ban nào?" / "thuộc phòng ban nào" / "ở phòng nào" / "phòng ban gì"
        if match_any(["thuộc phòng ban", "thuoc phong ban", "ở phòng ban", "o phong ban", "ở phòng nào", "o phong nao", "thuộc khoa nào", "thuoc khoa nao", "phòng ban nào", "phong ban nao", "phòng ban gì", "phong ban gi", "ở phòng gì", "o phong gi", "bộ phận nào", "bo phan nao", "phòng ban của", "phong ban cua"]):
            # Extract employee name or identifier
            name_match = re.search(r"(?:nhân viên|nhan vien|thông tin|thong tin|bạn|ban)\s+([a-zA-Z0-9\s_à-ỹÀ-Ỹ]+?)(?:\s+thuộc|\s+thuoc|\s+ở|\s+o|\s+phòng|\s+phong|\s+ban|\s*\?|$)", message, re.IGNORECASE)
            extracted_name = name_match.group(1).strip() if name_match else None
            if extracted_name and any(p in extracted_name.lower() for p in ["này", "nay", "đó", "do", "ấy", "ay", "kia", "nào", "nao"]):
                extracted_name = None

            identifier = emp_id or extracted_name or ctx_emp_name or "A"
            return {
                "tool": "get_employee_department",
                "parameters": {"identifier": identifier},
                "needs_more_info": False,
            }

        # 3. "Tìm thông tin nhân viên có mã ..." / "xem hồ sơ nhân viên"
        if emp_id and match_any(["thông tin", "thong tin", "hồ sơ", "ho so", "chi tiết", "chi tiet", "mã", "ma", "tìm", "tim", "người này", "nguoi nay", "bạn này", "ban nay"]):
            return {
                "tool": "get_employee_profile",
                "parameters": {"employee_id": emp_id},
                "needs_more_info": False,
            }

        # If asking for profile without ID
        if match_any(["xem hồ sơ", "xem ho so", "chi tiết nhân viên", "chi tiet nhan vien", "thông tin nhân viên", "thong tin nhan vien"]):
            if emp_id:
                return {
                    "tool": "get_employee_profile",
                    "parameters": {"employee_id": emp_id},
                    "needs_more_info": False,
                }
            return {
                "tool": None,
                "parameters": {},
                "needs_more_info": True,
                "clarification_message": "Vui lòng cung cấp mã nhân viên (ví dụ: NV001) để tôi tra cứu hồ sơ chi tiết giúp bạn.",
            }

        # 4. Department member count / Summary: "Phòng ban Kỹ thuật có bao nhiêu nhân viên?", "Phòng ... có bao nhiêu người"
        dept_count_match = re.search(r"phòng\s+(?:ban\s+)?([a-zA-Z\s_à-ỹÀ-Ỹ]+?)\s+có\s+bao\s+nhiêu\s+(?:nhân viên|người)", msg_lower)
        if not dept_count_match:
            dept_count_match = re.search(r"phong\s+(?:ban\s+)?([a-zA-Z\s_]+?)\s+co\s+bao\s+nhieu\s+(?:nhan vien|nguoi)", msg_no_dia)
        if dept_count_match:
            dept_name = dept_count_match.group(1).strip()
            return {
                "tool": "get_employee_summary",
                "parameters": {"department_id": dept_name},
                "needs_more_info": False,
            }

        if match_any(["thống kê nhân sự", "thong ke nhan su", "tổng số nhân viên", "tong so nhan vien", "có bao nhiêu nhân viên", "co bao nhieu nhan vien", "bao nhiêu người", "bao nhieu nguoi", "quy mô nhân sự", "quy mo nhan su"]):
            return {
                "tool": "get_employee_summary",
                "parameters": {},
                "needs_more_info": False,
            }

        # 5. Search employees: "tìm nhân viên", "danh sách nhân viên"
        if match_any(["danh sách nhân viên", "danh sach nhan vien", "toàn bộ nhân sự", "toan bo nhan su", "danh sách nhân sự", "danh sach nhan su"]):
            return {
                "tool": "search_employees",
                "parameters": {"limit": 10},
                "needs_more_info": False,
            }

        if match_any(["tìm nhân viên", "tim nhan vien", "tra cứu nhân viên", "tra cuu nhan vien"]):
            extracted = re.sub(r"^(?:tìm\s+(?:kiếm\s+)?nhân\s+viên\s*(?:có\s+tên|tên\s+là|tên)?|tra\s+cứu\s+nhân\s+viên)\s*", "", message, flags=re.IGNORECASE).strip()
            params = {"limit": 10}
            if extracted and len(extracted) > 1 and not any(k in extracted.lower() for k in ["nào", "đang", "toàn bộ", "tất cả"]):
                params["keyword"] = extracted
            return {
                "tool": "search_employees",
                "parameters": params,
                "needs_more_info": False,
            }

        # Fallback to search if keyword present
        clean_keyword = re.sub(r"^(?:cho tôi xem|cho toi xem|tìm|tim|hãy tìm|xem)\s+", "", message, flags=re.IGNORECASE).strip()
        return {
            "tool": "search_employees",
            "parameters": {"keyword": clean_keyword or message, "limit": 5},
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
            "Bạn là Trợ lý Nhân sự (Employee Agent) thông minh, chuyên nghiệp của hệ thống FME.\n"
            "Nhiệm vụ: Dựa vào DỮ LIỆU THỰC TẾ từ Tool vừa gọi để trả lời người dùng một cách chính xác, tự nhiên bằng tiếng Việt.\n"
            "QUY TẮC ĐỊNH DẠNG BẮT BUỘC:\n"
            "- Với chi tiết 1 bản ghi (như xem hồ sơ 1 nhân viên, phòng ban của 1 nhân viên): Trình bày dạng chi tiết / card rõ ràng với các mục bullet points. BẮT BUỘC ghi rõ Mã nhân viên (ví dụ: `NV001`), Họ và tên, Phòng ban, Chức vụ, Liên hệ (Email, SĐT). KHÔNG ép thành bảng 1 dòng.\n"
            "- Khi kết quả là danh sách từ 2 bản ghi trở lên (danh sách nhân viên, danh sách phòng ban...): BẮT BUỘC dùng bảng Markdown (Markdown Table) chuẩn. Cột đầu tiên là STT, tiếp đến Mã (Mã NV / Mã PB), rồi đến các cột thông tin.\n"
            "- Bảng có tiêu đề ngắn gọn (dùng ###). Cột số liệu (STT, số lượng nhân sự) phải căn phải (|---:|), các cột khác căn trái (|---|).\n"
            "- Sau bảng có MỘT dòng tổng kết ngắn gọn (ví dụ: **Tổng số:** X nhân viên / phòng ban.), KHÔNG lặp lại toàn bộ dữ liệu bên dưới.\n"
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
            "Hãy trả lời câu hỏi của người dùng dựa trên kết quả trên một cách tự nhiên, chính xác, định dạng Markdown đẹp mắt."
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
                f"### Thông tin phòng ban của nhân viên\n\n"
                f"- **Mã nhân viên:** `{emp_id}`\n"
                f"- **Họ và tên:** **{emp_name}**\n"
                f"- **Phòng ban:** **{dept_name}**\n"
                f"- **Chức vụ:** {position}"
            )

        if tool_name == "get_employee_profile":
            notes = f"\n- **Ghi chú:** {data.get('notes')}" if data.get("notes") else ""
            return (
                f"### Hồ sơ chi tiết nhân viên: {data.get('name')} [{data.get('id')}]\n\n"
                f"- **Mã nhân viên:** `{data.get('id')}`\n"
                f"- **Họ và tên:** **{data.get('name')}**\n"
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
            if not departments:
                return "Không tìm thấy thông tin phòng ban nào trong hệ thống."
            lines = [
                f"### Danh sách các phòng ban ({total} phòng ban)\n",
                "| STT | Mã PB | Tên phòng ban | Trưởng phòng | Nhân sự | Mô tả |",
                "|---:|---|---|---|---:|---|",
            ]
            for idx, d in enumerate(departments, 1):
                lines.append(
                    f"| {idx} | `{d.get('code')}` | {d.get('name')} | {d.get('manager_name')} | {d.get('member_count')} | {d.get('description', '')} |"
                )
            lines.append(f"\n**Tổng số:** {total} phòng ban.")
            return "\n".join(lines)

        if tool_name == "get_employee_summary":
            total = data.get("total_employees", 0)
            active = data.get("active_count", 0)
            by_dept = data.get("by_department", {})
            lines = [
                "### Báo cáo thống kê nhân sự\n",
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
            lines = [
                f"### Danh sách nhân viên (Tìm thấy {total} nhân viên)\n",
                "| STT | Mã NV | Họ và tên | Chức vụ | Phòng ban | Trạng thái |",
                "|---:|---|---|---|---|---|",
            ]
            for idx, e in enumerate(employees, 1):
                st = "Đang làm việc" if e.get("status") == "active" else e.get("status")
                lines.append(
                    f"| {idx} | `{e.get('id')}` | {e.get('name')} | {e.get('position')} | {e.get('department_name')} | {st} |"
                )
            lines.append(f"\n**Tổng số:** {total} nhân viên.")
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
