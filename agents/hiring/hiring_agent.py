"""Hiring Agent implementation extending BaseAgent."""

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
from mcp_servers.hiring.tools import HiringTools
from shared.logger import setup_logger
from .prompts import HIRING_AGENT_SYSTEM_PROMPT, INTENT_EXTRACTION_PROMPT

logger = setup_logger("fme.agent.hiring")


class HiringAgent(BaseAgent):
    """Domain Agent for the Hiring / Recruitment subsystem."""

    name: str = "hiring"

    def __init__(
        self,
        mcp_client: Optional[Any] = None,
        tools: Optional[HiringTools] = None,
        llm: Optional[BaseLLM] = None,
        openai_client: Optional[Any] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize HiringAgent.

        Args:
            mcp_client: Optional MCP Client (from Core team) to call MCP Server.
            tools: Optional direct HiringTools instance (used when MCP Client is not yet available).
            llm: Optional BaseLLM provider injected from LLMFactory.
            openai_client: Optional OpenAI client instance for legacy backward compatibility.
            model_name: OpenAI model to use.
        """
        self.mcp_client = mcp_client
        self.tools = tools or HiringTools()
        self.llm = llm
        self.openai_client = openai_client
        injected_model = getattr(getattr(llm, "config", None), "model", None)
        self.model_name = model_name or injected_model or os.getenv("OPENAI_MODEL", "openai/gpt-oss-120b")

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

        logger.info("[DomainAgent:Hiring] Bắt đầu xử lý request. LLM object tồn tại: %s, Class: %s", self.llm is not None, type(self.llm).__name__ if self.llm else "None")

        try:
            # 1. Parse intent & extract tool + parameters
            logger.info("[DomainAgent:Hiring] Bắt đầu intent classification cho message: '%s'", message)
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
                logger.info("[DomainAgent:Hiring] Không khớp tool cụ thể, chuyển sang câu hỏi tuyển dụng chung.")
                return self._handle_general_recruitment_query(message)

            # 3. Execute the tool (via MCP Client if present, or direct tools)
            logger.info("[DomainAgent:Hiring] Bắt đầu tool selection: đã chọn tool '%s' với params=%s", tool_name, params)
            logger.info("[DomainAgent:Hiring] Bắt đầu MCP tool call '%s'...", tool_name)
            tool_result = self._execute_tool(tool_name, params)
            logger.info("[DomainAgent:Hiring] Nhận kết quả từ MCP tool '%s': success=%s", tool_name, tool_result.get("success", False))

            # 4. Synthesize result into natural language response
            logger.info("[DomainAgent:Hiring] Bắt đầu response synthesis bằng LLM...")
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
        if self.mcp_client:
            try:
                if hasattr(self.mcp_client, "call_tool_sync"):
                    res = self.mcp_client.call_tool_sync("hiring", tool_name, params)
                    if hasattr(res, "success"):
                        return {"success": res.success, "data": res.data, "error": res.error, "metadata": getattr(res, "metadata", {})}
                    return res
                if hasattr(self.mcp_client, "call_tool"):
                    return self.mcp_client.call_tool("hiring", tool_name, params)
            except Exception as e:
                return {"success": False, "error": f"Lỗi gọi MCP Client: {str(e)}", "data": None}

        # Direct execution via HiringTools
        executor = self._tool_dispatch.get(tool_name)
        if not executor:
            return {"success": False, "error": f"Tool '{tool_name}' không tồn tại.", "data": None}

        return executor(**params)

    def _extract_intent(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Extract tool and parameters using injected LLM if available, otherwise rule-based matcher."""
        if (self.llm and not getattr(self.llm, "is_mock", False)) or (self.openai_client and (os.getenv("OPENAI_API_KEY") or getattr(self.openai_client, "api_key", None))):
            try:
                logger.info("[DomainAgent:Hiring] Thực hiện trích xuất intent qua LLM (model=%s)...", self.model_name)
                plan = self._extract_intent_with_llm(message, context)
                logger.info("[DomainAgent:Hiring] Trích xuất intent qua LLM thành công: %s", plan)
                return plan
            except Exception as exc:
                logger.warning("[DomainAgent:Hiring] Lỗi khi trích xuất intent qua LLM: %s. Fallback sang rule-based.", exc)
                return self._extract_intent_rule_based(message, context)

        logger.info("[DomainAgent:Hiring] Sử dụng rule-based matcher để trích xuất intent.")
        return self._extract_intent_rule_based(message, context)

    def _extract_intent_with_llm(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Use LLM (or fallback OpenAI client) to parse intent and return structured JSON."""
        messages = [
            {"role": "system", "content": INTENT_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Yêu cầu: {message}\nNgữ cảnh trước: {json.dumps(context or {}, ensure_ascii=False)}"},
        ]

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
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            return json.loads(content)

        return self._extract_intent_rule_based(message, context)

    def _extract_intent_rule_based(self, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Reliable rule-based matcher for development and offline testing."""
        msg = message.lower()
        msg_norm = unicodedata.normalize("NFD", msg)
        msg_no_dia = "".join(ch for ch in msg_norm if unicodedata.category(ch) != "Mn").replace("đ", "d").replace("Đ", "D")

        def match_any(keywords):
            return any(k in msg or k in msg_no_dia for k in keywords)

        # 1. Candidate detail query: "thông tin ứng viên ...", "mã UV001", "hồ sơ ứng viên"
        uv_match = re.search(r"\b(uv\d{3,5})\b", msg, re.IGNORECASE)
        candidate_id = None
        if uv_match:
            candidate_id = uv_match.group(1).upper()
        elif context:
            candidate_id = context.get("last_candidate_id") or context.get("last_mentioned_candidate_id")

        if uv_match:
            return {"tool": "get_candidate_detail", "parameters": {"candidate_id": candidate_id}}

        if match_any(["thông tin ứng viên", "hồ sơ ứng viên", "chi tiết ứng viên", "ứng viên này", "bạn này", "người này"]):
            if candidate_id:
                return {"tool": "get_candidate_detail", "parameters": {"candidate_id": candidate_id}}
            return {
                "needs_more_info": True,
                "clarification_message": "Vui lòng cung cấp mã ứng viên (ví dụ: UV001) hoặc tên ứng viên để tôi tra cứu chi tiết.",
            }

        # 2. Interview schedule: "lịch phỏng vấn", "khi nào phỏng vấn", "phỏng vấn tuần này"
        if match_any(["lịch phỏng vấn", "lịch pv", "khi nào phỏng vấn", "danh sách phỏng vấn"]):
            params = {}
            if match_any(["tuần này", "hôm nay", "tháng 8"]):
                # Default current demo month
                params["from_date"] = "2026-08-01"
                params["to_date"] = "2026-08-31"
            return {"tool": "get_interview_schedule", "parameters": params}

        # 3. Candidates search by status: "chờ phỏng vấn", "đang phỏng vấn", "đã tuyển dụng", statuses
        status_map = {
            "pending_interview": ["chờ phỏng vấn", "chờ pv", "pending_interview"],
            "interviewing": ["đang phỏng vấn", "phỏng vấn vòng", "interviewing"],
            "offered": ["đã gửi thư mời", "offered", "nhận offer"],
            "hired": ["đã tuyển dụng", "được tuyển dụng", "trúng tuyển", "hired", "đã vào làm"],
            "rejected": ["bị từ chối", "từ chối", "rejected"],
            "screening": ["sàng lọc", "screening", "duyệt hồ sơ"],
            "applied": ["mới nộp", "applied", "mới ứng tuyển"],
        }
        for status_code, keywords in status_map.items():
            if match_any(keywords):
                return {"tool": "search_candidates", "parameters": {"status": status_code}}

        # 4. Job openings: "vị trí đang tuyển", "vị trí tuyển dụng", "đang tuyển những vị trí nào", "job openings"
        if match_any(["vị trí đang tuyển", "vị trí tuyển dụng", "đang tuyển", "danh sách tuyển dụng", "job"]):
            dept = None
            if match_any(["công nghệ", "it", "ai", "backend"]):
                dept = "Khối Công nghệ thông tin"
            elif match_any(["dữ liệu", "data"]):
                dept = "Khối Dữ liệu & AI"
            elif match_any(["nhân sự", "hr"]):
                dept = "Phòng Nhân sự"
            elif match_any(["vận hành", "devops", "sre"]):
                dept = "Khối Vận hành"
            params = {"status": "open"}
            if dept:
                params["department"] = dept
            return {"tool": "list_job_openings", "parameters": params}

        # 5. Recruitment summary / statistics: "tổng hợp", "tình hình tuyển dụng", "thống kê tuyển dụng", "báo cáo tuyển dụng"
        if match_any(["tổng hợp", "thống kê", "tình hình tuyển dụng", "báo cáo tuyển dụng", "tổng số ứng viên"]):
            return {"tool": "get_recruitment_summary", "parameters": {}}

        # 6. General candidate search: "tìm ứng viên", "danh sách ứng viên", "ứng viên backend", etc.
        if match_any(["tìm ứng viên", "tìm kiếm ứng viên", "ứng viên", "danh sách ứng viên"]):
            kw = None
            for title in ["backend", "ai", "machine learning", "dữ liệu", "data", "nhân sự", "devops", "sre", "react", "python", "java"]:
                if title in msg or title in msg_no_dia:
                    kw = title
                    break
            if not kw:
                extracted = re.sub(r"^(?:tìm\s+(?:kiếm\s+)?ứng\s+viên\s*(?:có\s+kỹ\s+năng|kỹ\s+năng)?|ứng\s+viên\s*(?:có\s+kỹ\s+năng|kỹ\s+năng)?|danh\s+sách\s+ứng\s+viên)\s*", "", message, flags=re.IGNORECASE).strip()
                if extracted and len(extracted) > 1 and not any(k in extracted.lower() for k in ["nào", "đang", "toàn bộ", "tất cả"]):
                    kw = extracted

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
        system_prompt = (
            "Bạn là Trợ lý Tuyển dụng (Hiring Agent) thông minh, chuyên nghiệp của hệ thống FME.\n"
            "Nhiệm vụ: Dựa vào DỮ LIỆU THỰC TẾ từ Tool vừa gọi để trả lời người dùng một cách chính xác, tự nhiên bằng tiếng Việt.\n\n"
            "QUY TẮC ĐỊNH DẠNG BẮT BUỘC:\n"
            "1. KHI KẾT QUẢ TOOL LÀ DANH SÁCH TỪ 2 BẢN GHI TRỞ LÊN (kể cả khi người dùng hỏi 'Có bao nhiêu...', 'Bao nhiêu người...', hay 'Danh sách...'):\n"
            "- BẮT BUỘC trả lời số lượng tổng quan, VÀ NGAY SAU ĐÓ BẮT BUỘC PHẢI CÓ TIÊU ĐỀ (###) KÈM BẢNG MARKDOWN (Markdown Table) CHUẨN chứa đầy đủ các bản ghi. Tuyệt đối không được bỏ qua bảng dữ liệu!\n"
            "- Với danh sách ứng viên (search_candidates): Dùng đúng 7 cột chuẩn:\n"
            "  | STT | Mã CV | Họ và tên | Vị trí | Kinh nghiệm | Trạng thái | Ngày nộp |\n"
            "  Cột STT và Kinh nghiệm căn phải (|---:|), các cột khác căn trái.\n"
            "- Với danh sách vị trí tuyển dụng (list_job_openings):\n"
            "  | STT | Mã vị trí | Tiêu đề công việc | Phòng ban | Chỉ tiêu | Mức lương |\n"
            "  Cột STT và Chỉ tiêu căn phải (|---:|).\n"
            "- Với lịch phỏng vấn (get_interview_schedule):\n"
            "  | STT | Mã UV | Ứng viên | Vị trí | Thời gian | Vòng | Người phỏng vấn | Trạng thái |\n"
            "- BẮT BUỘC dịch Trạng thái sang tiếng Việt:\n"
            "  pending_interview -> Chờ phỏng vấn\n"
            "  interviewing -> Đang phỏng vấn\n"
            "  screening -> Đang duyệt hồ sơ\n"
            "  offered -> Đã gửi thư mời\n"
            "  rejected -> Đã từ chối\n"
            "  hired -> Đã nhận việc\n"
            "  applied -> Mới nộp\n"
            "  open -> Đang mở tuyển dụng\n"
            "  closed -> Đã đóng\n"
            "- Sau bảng có MỘT dòng tổng kết: **Tổng số:** X bản ghi.\n"
            "- KHÔNG chèn các cột dài như kỹ năng, ghi chú, liên hệ vào bảng làm vỡ giao diện.\n\n"
            "2. VỚI CHI TIẾT 1 BẢN GHI (như xem hồ sơ 1 ứng viên, 1 vị trí): Trình bày dạng chi tiết / card rõ ràng với các mục bullet points. BẮT BUỘC ghi rõ Mã định danh (`UV001`), Họ và tên, Vị trí, Trạng thái tiếng Việt, Kinh nghiệm, Kỹ năng, Liên hệ, Ghi chú. KHÔNG ép thành bảng 1 dòng.\n\n"
            "3. KHI KHÔNG TÌM THẤY BẢN GHI NÀO: Thông báo lịch sự, không vẽ bảng rỗng.\n\n"
            "4. KÝ TỰ: Tuyệt đối KHÔNG escape gạch đứng | thành \\| và KHÔNG escape email @ thành \\@."
        )
        user_prompt = (
            f"Câu hỏi của người dùng: {user_message}\n\n"
            f"Tool đã gọi: {tool_name}\n"
            f"Dữ liệu Tool trả về:\n{json.dumps(data, ensure_ascii=False, indent=2)}"
        )

        resp_text = None
        if self.llm and not getattr(self.llm, "is_mock", False):
            try:
                req = LLMRequest(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    model=self.model_name,
                    temperature=0.2,
                )
                logger.info("[DomainAgent:Hiring] Gọi self.llm.generate() để tổng hợp câu trả lời...")
                resp = self.llm.generate(req)
                if resp.content and resp.content.strip():
                    logger.info("[DomainAgent:Hiring] LLM tổng hợp câu trả lời thành công.")
                    resp_text = resp.content.strip()
            except Exception as exc:
                logger.warning("[DomainAgent:Hiring] Lỗi khi tổng hợp câu trả lời qua LLM: %s. Fallback sang template format.", exc)
        elif self.openai_client:
            try:
                response = self.openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.2,
                )
                content = response.choices[0].message.content
                if content and content.strip():
                    resp_text = content.strip()
            except Exception as exc:
                logger.warning("[DomainAgent:Hiring] Lỗi OpenAI client khi tổng hợp câu trả lời: %s", exc)

        if resp_text:
            # Safeguard: if tool returned multi-record list but LLM response omitted the table, append it
            if tool_name == "search_candidates" and len(data.get("candidates", [])) >= 2:
                if "| STT" not in resp_text and "| Mã" not in resp_text:
                    table_md = self._format_candidates_table(data, params)
                    resp_text = f"{resp_text}\n\n{table_md}"
            elif tool_name == "list_job_openings" and len(data.get("job_openings", [])) >= 2:
                if "| STT" not in resp_text and "| Mã" not in resp_text:
                    table_md = self._format_jobs_table(data)
                    resp_text = f"{resp_text}\n\n{table_md}"
            elif tool_name == "get_interview_schedule" and len(data.get("schedules", [])) >= 2:
                if "| STT" not in resp_text and "| Mã" not in resp_text:
                    table_md = self._format_schedules_table(data)
                    resp_text = f"{resp_text}\n\n{table_md}"
            return resp_text

        logger.info("[DomainAgent:Hiring] Sử dụng template fallback format.")

        # 2. Template fallback if LLM is unavailable or failed
        if tool_name == "search_candidates":
            return self._format_candidates_table(data, params)
        elif tool_name == "get_candidate_detail":
            return self._format_candidate_detail_card(data)
        elif tool_name == "list_job_openings":
            return self._format_jobs_table(data)
        elif tool_name == "get_interview_schedule":
            return self._format_schedules_table(data)
        elif tool_name == "get_recruitment_summary":
            return self._format_recruitment_summary(data)
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _format_candidates_table(self, data: Dict[str, Any], params: Dict[str, Any]) -> str:
        """Format candidate search result into standard Markdown table."""
        candidates = data.get("candidates", [])
        total = data.get("total_found", len(candidates))
        if not candidates:
            return "Hiện tại không tìm thấy ứng viên nào phù hợp với điều kiện tra cứu."

        status_filter = params.get("status")
        status_desc = f" có trạng thái '{status_filter}'" if status_filter else ""
        status_map = {
            "pending_interview": "Chờ phỏng vấn",
            "interviewing": "Đang phỏng vấn",
            "screening": "Đang duyệt hồ sơ",
            "offered": "Đã gửi thư mời",
            "rejected": "Đã từ chối",
            "hired": "Đã nhận việc",
            "applied": "Mới nộp",
        }

        lines = [
            f"### Danh sách ứng viên (Tìm thấy {total} ứng viên{status_desc})\n",
            "| STT | Mã CV | Họ và tên | Vị trí | Kinh nghiệm | Trạng thái | Ngày nộp |",
            "|---:|---|---|---|---:|---|---|",
        ]
        for idx, c in enumerate(candidates, 1):
            st_vn = status_map.get(c.get("status"), c.get("status"))
            exp = f"{c.get('experience_years', 0)} năm"
            lines.append(
                f"| {idx} | {c.get('id')} | {c.get('name')} | {c.get('position')} | {exp} | {st_vn} | {c.get('applied_date', '-')} |"
            )
        lines.append(f"\n**Tổng số:** {total} ứng viên.")
        return "\n".join(lines)

    def _format_candidate_detail_card(self, c: Dict[str, Any]) -> str:
        """Format single candidate detail card."""
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
            f"### Hồ sơ chi tiết ứng viên: {c.get('name')} [{c.get('id')}]\n\n"
            f"- **Mã ứng viên:** `{c.get('id')}`\n"
            f"- **Họ và tên:** **{c.get('name')}**\n"
            f"- **Vị trí ứng tuyển:** {c.get('position')} (Mã vị trí: `{c.get('job_id')}`)\n"
            f"- **Trạng thái hiện tại:** {status_vn}\n"
            f"- **Kinh nghiệm:** {c.get('experience_years')} năm\n"
            f"- **Kỹ năng chính:** {', '.join(c.get('skills', []))}\n"
            f"- **Liên hệ:** Email: {c.get('email')} | SĐT: {c.get('phone')}\n"
            f"- **Ngày nộp hồ sơ:** {c.get('applied_date')}\n"
            f"- **Ghi chú:** {c.get('notes', 'Không có')}"
        )

    def _format_jobs_table(self, data: Dict[str, Any]) -> str:
        """Format job openings into standard Markdown table."""
        jobs = data.get("job_openings", [])
        total = data.get("total_found", len(jobs))
        if not jobs:
            return "Hiện tại không có vị trí tuyển dụng nào phù hợp với yêu cầu."

        lines = [
            f"### Danh sách các vị trí đang tuyển dụng ({total} vị trí)\n",
            "| STT | Mã vị trí | Tiêu đề công việc | Phòng ban | Chỉ tiêu | Mức lương |",
            "|---:|---|---|---|---:|---|",
        ]
        for idx, j in enumerate(jobs, 1):
            lines.append(
                f"| {idx} | `{j.get('id')}` | {j.get('title')} | {j.get('department')} | {j.get('open_positions')} | {j.get('salary_range')} |"
            )
        lines.append(f"\n**Tổng số:** {total} vị trí đang tuyển dụng.")
        return "\n".join(lines)

    def _format_schedules_table(self, data: Dict[str, Any]) -> str:
        """Format interview schedules into standard Markdown table."""
        schedules = data.get("schedules", [])
        total = data.get("total_found", len(schedules))
        if not schedules:
            return "Hiện tại không có lịch phỏng vấn nào được lên lịch trong khoảng thời gian này."

        lines = [
            f"### Lịch phỏng vấn ({total} buổi phỏng vấn)\n",
            "| STT | Mã UV | Ứng viên | Vị trí | Thời gian | Vòng | Người phỏng vấn | Trạng thái |",
            "|---:|---|---|---|---|---:|---|---|",
        ]
        for idx, s in enumerate(schedules, 1):
            time_str = f"{s.get('interview_time')} ngày {s.get('interview_date')}"
            lines.append(
                f"| {idx} | `{s.get('candidate_id')}` | **{s.get('candidate_name')}** | {s.get('job_title')} | {time_str} | {s.get('round')} | {s.get('interviewer')} | {s.get('status')} |"
            )
        lines.append(f"\n**Tổng số:** {total} buổi phỏng vấn.")
        return "\n".join(lines)

    def _format_recruitment_summary(self, data: Dict[str, Any]) -> str:
        """Format recruitment summary statistics."""
        s = data
        lines = [
            "### Tổng hợp tình hình Tuyển dụng\n",
            f"- **Tổng số chỉ tiêu đang mở:** **{s.get('total_openings')}** vị trí",
            f"- **Tổng số ứng viên trong hệ thống:** **{s.get('total_candidates')}** ứng viên",
            f"- **Ứng viên chờ phỏng vấn:** {s.get('pending_interview_count')} ứng viên",
            f"- **Ứng viên đang phỏng vấn:** {s.get('interviewing_count')} ứng viên",
            f"- **Ứng viên đã gửi thư mời (Offered):** {s.get('offered_count')} ứng viên",
            f"- **Ứng viên đã từ chối:** {s.get('rejected_count')} ứng viên\n",
            "**Chỉ tiêu tuyển dụng theo phòng ban:**",
        ]
        for dept, count in s.get("by_department", {}).items():
            lines.append(f"- **{dept}:** {count} chỉ tiêu")
        return "\n".join(lines)

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

    def _handle_general_query(self, message: str) -> AgentResponse:
        """Alias for general query compatibility across all domain agents."""
        return self._handle_general_recruitment_query(message)
