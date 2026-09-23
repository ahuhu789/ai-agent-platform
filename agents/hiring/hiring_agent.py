"""Hiring Agent implementation extending BaseAgent."""

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
from mcp_servers.hiring.tools import HiringTools
from .prompts import HIRING_AGENT_SYSTEM_PROMPT, INTENT_EXTRACTION_PROMPT


class HiringAgent(BaseAgent):
    """Domain Agent for the Hiring / Recruitment subsystem."""

    name: str = "hiring"

    def __init__(
        self,
        mcp_client: Optional[Any] = None,
        tools: Optional[HiringTools] = None,
        openai_client: Optional[Any] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize HiringAgent.

        Args:
            mcp_client: Optional MCP Client (from Core team) to call MCP Server.
            tools: Optional direct HiringTools instance (used when MCP Client is not yet available).
            openai_client: Optional OpenAI client instance for LLM intent parsing & synthesis.
            model_name: OpenAI model to use.
        """
        self.mcp_client = mcp_client
        self.tools = tools or HiringTools()
        
        # Auto-initialize OpenAI client from environment if available and not explicitly provided
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

        # Map tool names to methods
        self._tool_dispatch: Dict[str, Callable] = {
            "search_candidates": self.tools.search_candidates,
            "get_candidate_detail": self.tools.get_candidate_detail,
            "list_job_openings": self.tools.list_job_openings,
            "get_interview_schedule": self.tools.get_interview_schedule,
            "get_recruitment_summary": self.tools.get_recruitment_summary,
        }

    def handle(self, request: AgentRequest) -> AgentResponse:
        """Handle an incoming user message routed from Root Agent."""
        message = request.message.strip()
        if not message:
            return AgentResponse(
                success=False,
                error="Nội dung yêu cầu trống.",
                metadata={"source": "hiring", "agent": self.name},
            )

        try:
            # 1. Parse intent & extract tool + parameters
            plan = self._extract_intent(message, request.context)

            # 2. Check if we need more clarification from the user
            if plan.get("needs_more_info"):
                clarification = plan.get("clarification_message") or "Vui lòng cung cấp thêm thông tin để tôi hỗ trợ bạn tốt nhất."
                return AgentResponse(
                    success=True,
                    data={"response": clarification, "status": "needs_more_info"},
                    metadata={"source": "hiring", "agent": self.name, "tool_used": None},
                )

            tool_name = plan.get("tool")
            params = plan.get("parameters", {})

            if not tool_name or tool_name not in self._tool_dispatch:
                # Fallback if no specific tool matched
                return self._handle_general_recruitment_query(message)

            # 3. Execute the tool (via MCP Client if present, or direct tools)
            tool_result = self._execute_tool(tool_name, params)

            # 4. Synthesize result into natural language response
            synthesized_answer = self._synthesize_response(message, tool_name, params, tool_result)

            return AgentResponse(
                success=tool_result.get("success", False),
                data={
                    "response": synthesized_answer,
                    "raw_tool_result": tool_result.get("data"),
                    "tool_used": tool_name,
                    "parameters": params,
                },
                error=tool_result.get("error"),
                metadata={
                    "source": "hiring",
                    "agent": self.name,
                    "tool_used": tool_name,
                    "conversation_id": request.conversation_id,
                    "user_id": request.user_id,
                },
            )

        except Exception as e:
            return AgentResponse(
                success=False,
                error=f"Lỗi xử lý yêu cầu tuyển dụng: {str(e)}",
                metadata={"source": "hiring", "agent": self.name},
            )

    def _execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool through MCP Client if configured, or fall back to internal tool dispatcher."""
        if self.mcp_client and hasattr(self.mcp_client, "call_tool"):
            # When Core team's MCP Client is available
            try:
                return self.mcp_client.call_tool("hiring", tool_name, params)
            except Exception as e:
                return {"success": False, "error": f"Lỗi gọi MCP Client: {str(e)}", "data": None}

        # Direct execution via HiringTools
        executor = self._tool_dispatch.get(tool_name)
        if not executor:
            return {"success": False, "error": f"Tool '{tool_name}' không tồn tại.", "data": None}

        return executor(**params)

    def _extract_intent(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract tool and parameters using OpenAI LLM if available, otherwise rule-based matcher."""
        if self.openai_client and (os.getenv("OPENAI_API_KEY") or getattr(self.openai_client, "api_key", None)):
            try:
                return self._extract_intent_with_llm(message, context)
            except Exception:
                # Fallback to rule-based matcher on any LLM API error
                return self._extract_intent_rule_based(message)

        return self._extract_intent_rule_based(message)

    def _extract_intent_with_llm(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Use OpenAI LLM to parse intent and return structured JSON."""
        messages = [
            {"role": "system", "content": INTENT_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Yêu cầu: {message}\nNgữ cảnh trước: {json.dumps(context or {}, ensure_ascii=False)}"},
        ]
        response = self.openai_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        return json.loads(content)

    def _extract_intent_rule_based(self, message: str) -> Dict[str, Any]:
        """Reliable rule-based matcher for development and offline testing."""
        msg = message.lower()

        # 1. Candidate detail query: "thông tin ứng viên ...", "mã UV001", "hồ sơ ứng viên"
        uv_match = re.search(r"\b(uv\d{3,4})\b", msg, re.IGNORECASE)
        if uv_match:
            candidate_id = uv_match.group(1).upper()
            return {"tool": "get_candidate_detail", "parameters": {"candidate_id": candidate_id}}

        if any(k in msg for k in ["thông tin ứng viên", "hồ sơ ứng viên", "chi tiết ứng viên"]):
            return {
                "needs_more_info": True,
                "clarification_message": "Vui lòng cung cấp mã ứng viên (ví dụ: UV001) hoặc tên ứng viên để tôi tra cứu chi tiết.",
            }

        # 2. Interview schedule: "lịch phỏng vấn", "khi nào phỏng vấn", "phỏng vấn tuần này"
        if any(k in msg for k in ["lịch phỏng vấn", "lịch pv", "khi nào phỏng vấn", "danh sách phỏng vấn"]):
            params = {}
            if "tuần này" in msg or "hôm nay" in msg or "tháng 8" in msg:
                # Default current demo month
                params["from_date"] = "2026-08-01"
                params["to_date"] = "2026-08-31"
            return {"tool": "get_interview_schedule", "parameters": params}

        # 3. Candidates waiting for interview: "bao nhiêu ứng viên đang chờ phỏng vấn", "ứng viên chờ phỏng vấn"
        if "chờ phỏng vấn" in msg or "chờ pv" in msg or "pending_interview" in msg:
            return {"tool": "search_candidates", "parameters": {"status": "pending_interview"}}

        # 4. Job openings: "vị trí đang tuyển", "vị trí tuyển dụng", "đang tuyển những vị trí nào", "job openings"
        if any(k in msg for k in ["vị trí đang tuyển", "vị trí tuyển dụng", "đang tuyển", "danh sách tuyển dụng", "job"]):
            dept = None
            if any(k in msg for k in ["công nghệ", "it", "ai", "backend"]):
                dept = "Khối Công nghệ thông tin"
            elif any(k in msg for k in ["dữ liệu", "data"]):
                dept = "Khối Dữ liệu & AI"
            elif any(k in msg for k in ["nhân sự", "hr"]):
                dept = "Phòng Nhân sự"
            elif any(k in msg for k in ["vận hành", "devops", "sre"]):
                dept = "Khối Vận hành"
            params = {"status": "open"}
            if dept:
                params["department"] = dept
            return {"tool": "list_job_openings", "parameters": params}

        # 5. Recruitment summary / statistics: "tổng hợp", "tình hình tuyển dụng", "thống kê tuyển dụng", "báo cáo tuyển dụng"
        if any(k in msg for k in ["tổng hợp", "thống kê", "tình hình tuyển dụng", "báo cáo tuyển dụng", "tổng số ứng viên"]):
            return {"tool": "get_recruitment_summary", "parameters": {}}

        # 6. General candidate search: "tìm ứng viên", "danh sách ứng viên", "ứng viên backend", etc.
        if any(k in msg for k in ["tìm ứng viên", "ứng viên", "danh sách ứng viên"]):
            kw = None
            for title in ["backend", "ai", "machine learning", "dữ liệu", "data", "nhân sự", "devops", "sre"]:
                if title in msg:
                    kw = title
                    break
            params = {}
            if kw:
                params["keyword"] = kw
            return {"tool": "search_candidates", "parameters": params}

        # 7. General greeting or help request
        if any(k in msg for k in ["xin chào", "chào bạn", "hello", "hi", "giúp gì", "làm được gì", "hướng dẫn", "bạn là ai"]):
            return {"tool": None, "parameters": {}}

        # Default to recruitment summary as fallback overview
        return {"tool": "get_recruitment_summary", "parameters": {}}

    def _synthesize_response(
        self,
        user_message: str,
        tool_name: str,
        params: Dict[str, Any],
        tool_result: Dict[str, Any],
    ) -> str:
        """Synthesize tool result into clear, friendly Vietnamese text using LLM if available, otherwise template."""
        if not tool_result.get("success"):
            err = tool_result.get("error", "Đã xảy ra lỗi không xác định.")
            return f" Không thể thực hiện tra cứu: {err}"

        data = tool_result.get("data", {})

        # 1. Natural LLM Synthesis: if LLM client is available, format answer exactly as requested
        if self.openai_client:
            try:
                system_prompt = (
                    "Bạn là Trợ lý Tuyển dụng (Hiring Agent) thông minh, thân thiện của hệ thống FME.\n"
                    "Nhiệm vụ: Dựa vào DỮ LIỆU THỰC TẾ từ Tool vừa gọi để trả lời người dùng một cách chính xác, tự nhiên bằng tiếng Việt.\n"
                    "QUY TẮC BẮT BUỘC:\n"
                    "- Tuân thủ chính xác yêu cầu của người dùng (ví dụ: nếu yêu cầu 'chỉ lấy tên' thì chỉ xuất danh sách tên, nếu hỏi 'có mấy người' thì trả lời số lượng).\n"
                    "- Không bịa đặt thông tin ngoài dữ liệu được cung cấp.\n"
                    "- Định dạng câu trả lời rõ ràng, dễ đọc (dùng gạch đầu dòng Markdown nếu liệt kê)."
                )
                user_prompt = (
                    f"Câu hỏi của người dùng: {user_message}\n\n"
                    f"Tool đã gọi: {tool_name}\n"
                    f"Dữ liệu Tool trả về:\n{json.dumps(data, ensure_ascii=False, indent=2)}"
                )
                response = self.openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.3,
                )
                content = response.choices[0].message.content
                if content and content.strip():
                    return content.strip()
            except Exception:
                pass

        # 2. Template fallback if LLM is unavailable or failed
        if tool_name == "search_candidates":
            candidates = data.get("candidates", [])
            total = data.get("total_found", len(candidates))
            if not candidates:
                return "Hiện tại không tìm thấy ứng viên nào phù hợp với điều kiện tra cứu."

            status_filter = params.get("status")
            status_desc = f" có trạng thái '{status_filter}'" if status_filter else ""
            lines = [f"📋 **Tìm thấy {total} ứng viên{status_desc}:**\n"]
            for c in candidates:
                status_vn = {
                    "pending_interview": "Chờ phỏng vấn",
                    "interviewing": "Đang phỏng vấn",
                    "screening": "Đang duyệt hồ sơ",
                    "offered": "Đã gửi thư mời",
                    "rejected": "Đã từ chối",
                    "hired": "Đã nhận việc",
                    "applied": "Mới nộp",
                }.get(c.get("status"), c.get("status"))

                lines.append(
                    f"• **[{c['id']}] {c['name']}** - {c['position']}\n"
                    f"  - Email: {c['email']} | SĐT: {c['phone']}\n"
                    f"  - Kinh nghiệm: {c['experience_years']} năm | Trạng thái: {status_vn}\n"
                    f"  - Kỹ năng: {', '.join(c.get('skills', []))}"
                )
            return "\n".join(lines)

        # 2. get_candidate_detail synthesis
        elif tool_name == "get_candidate_detail":
            c = data
            status_vn = {
                "pending_interview": "Chờ phỏng vấn",
                "interviewing": "Đang phỏng vấn",
                "screening": "Đang duyệt hồ sơ",
                "offered": "Đã gửi thư mời nhận việc",
                "rejected": "Đã từ chối",
                "hired": "Đã nhận việc",
                "applied": "Mới nộp hồ sơ",
            }.get(c.get("status"), c.get("status"))

            return (
                f"👤 **Hồ sơ chi tiết ứng viên: {c.get('name')} [{c.get('id')}]**\n\n"
                f"• **Vị trí ứng tuyển:** {c.get('position')} (Mã vị trí: {c.get('job_id')})\n"
                f"• **Trạng thái hiện tại:** {status_vn}\n"
                f"• **Kinh nghiệm:** {c.get('experience_years')} năm\n"
                f"• **Kỹ năng chính:** {', '.join(c.get('skills', []))}\n"
                f"• **Liên hệ:** Email: {c.get('email')} | SĐT: {c.get('phone')}\n"
                f"• **Ngày nộp hồ sơ:** {c.get('applied_date')}\n"
                f"• **Ghi chú tuyển dụng:** {c.get('notes', 'Không có')}"
            )

        # 3. list_job_openings synthesis
        elif tool_name == "list_job_openings":
            jobs = data.get("job_openings", [])
            total = data.get("total_found", len(jobs))
            if not jobs:
                return "Hiện tại không có vị trí tuyển dụng nào phù hợp với yêu cầu."

            lines = [f"🏥 **Danh sách các vị trí đang tuyển dụng ({total} vị trí):**\n"]
            for j in jobs:
                lines.append(
                    f"• **[{j['id']}] {j['title']}** ({j['department']})\n"
                    f"  - Số lượng cần tuyển: **{j['open_positions']} chỉ tiêu**\n"
                    f"  - Mức lương: {j['salary_range']}\n"
                    f"  - Yêu cầu: {'; '.join(j.get('requirements', []))}"
                )
            return "\n".join(lines)

        # 4. get_interview_schedule synthesis
        elif tool_name == "get_interview_schedule":
            schedules = data.get("schedules", [])
            total = data.get("total_found", len(schedules))
            if not schedules:
                return "Hiện tại không có lịch phỏng vấn nào được lên lịch trong khoảng thời gian này."

            lines = [f"📅 **Lịch phỏng vấn ({total} buổi phỏng vấn):**\n"]
            for s in schedules:
                lines.append(
                    f"• **Ứng viên: {s['candidate_name']} [{s['candidate_id']}]** - Vị trí: {s['job_title']}\n"
                    f"  - Thời gian: **{s['interview_time']} ngày {s['interview_date']}** (Vòng {s['round']})\n"
                    f"  - Người phỏng vấn: {s['interviewer']}\n"
                    f"  - Trạng thái: {s['status']}"
                )
            return "\n".join(lines)

        # 5. get_recruitment_summary synthesis
        elif tool_name == "get_recruitment_summary":
            s = data
            lines = [
                "📊 **Tổng hợp tình hình Tuyển dụng:**\n",
                f"• **Tổng số chỉ tiêu đang mở:** {s.get('total_openings')} vị trí",
                f"• **Tổng số ứng viên trong hệ thống:** {s.get('total_candidates')} ứng viên",
                f"• **Ứng viên chờ phỏng vấn:** {s.get('pending_interview_count')} ứng viên",
                f"• **Ứng viên đang phỏng vấn:** {s.get('interviewing_count')} ứng viên",
                f"• **Ứng viên đã gửi thư mời (Offered):** {s.get('offered_count')} ứng viên",
                f"• **Ứng viên đã từ chối:** {s.get('rejected_count')} ứng viên",
                "\n**Chỉ tiêu tuyển dụng theo phòng ban:**",
            ]
            for dept, count in s.get("by_department", {}).items():
                lines.append(f"  - {dept}: {count} chỉ tiêu")

            return "\n".join(lines)

        return json.dumps(data, ensure_ascii=False, indent=2)

    def _handle_general_recruitment_query(self, message: str) -> AgentResponse:
        """Handle general greetings or broad questions about the recruitment subsystem."""
        help_text = (
            "Xin chào! Tôi là Trợ lý Tuyển dụng (Hiring Agent). Tôi có thể giúp bạn:\n"
            "1. Tra cứu danh sách vị trí đang tuyển (ví dụ: 'Danh sách vị trí đang tuyển là gì?')\n"
            "2. Thống kê ứng viên chờ phỏng vấn (ví dụ: 'Có bao nhiêu ứng viên đang chờ phỏng vấn?')\n"
            "3. Xem thông tin chi tiết ứng viên (ví dụ: 'Cho tôi thông tin ứng viên có mã UV001')\n"
            "4. Tra cứu lịch phỏng vấn (ví dụ: 'Lịch phỏng vấn tuần này?')\n"
            "5. Báo cáo tổng hợp tình hình tuyển dụng (ví dụ: 'Tổng hợp tình hình tuyển dụng')"
        )
        return AgentResponse(
            success=True,
            data={"response": help_text},
            metadata={"source": "hiring", "agent": self.name, "tool_used": None},
        )
