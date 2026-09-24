import re
import json
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

import os
import sys

from agents.contract import BaseAgent, AgentRequest, AgentResponse
from agents.mcp_client import MCPClient

try:
    from core.memory import get_session_history
except ImportError:
    get_session_history = None

try:
    from core.llm import get_chat_model
except ImportError:
    get_chat_model = None

try:
    from shared.llm import load_config, LLMFactory, LLMRequest
except ImportError:
    load_config = None
    LLMFactory = None
    LLMRequest = None

class AttendanceAgent(BaseAgent):
    name = "attendance"
    
    def __init__(self):
        # Khởi tạo MCP client
        self.mcp_client = MCPClient()

    def _get_today_date(self) -> str:
        """
        Lấy ngày hôm nay thực tế theo hệ thống (YYYY-MM-DD).
        """
        return datetime.now().strftime("%Y-%m-%d")

    def _get_system_latest_date(self) -> str:
        """
        Lấy ngày có dữ liệu chấm công mới nhất từ Repository (để tham khảo khi ngày hiện tại chưa có dữ liệu).
        """
        try:
            from integrations.my_enterprise_attendance.repository import get_repository
            return get_repository().get_latest_attendance_date()
        except Exception:
            return "2026-09-12"

    def _parse_date_from_message(self, message: str, today_date: Optional[str] = None) -> Optional[str]:
        """
        Trích xuất ngày từ câu hỏi tiếng Việt:
        - 'hôm nay', 'today' -> today_date
        - 'hôm qua', 'yesterday' -> today_date - 1 day
        - 'ngày 18 tháng 9', '18 tháng 9', '18 tháng 09 năm 2026' -> '2026-09-18'
        - '2026-09-18' -> '2026-09-18'
        - '18/09/2026', '18/9', '18-09' -> '2026-09-18'
        """
        if today_date is None:
            today_date = self._get_today_date()
        lower = message.lower()
        if re.search(r'(hôm nay|ngày hôm nay|today)', lower):
            return today_date
        if re.search(r'(hôm qua|ngày hôm qua|yesterday)', lower):
            return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        # 1. Định dạng: ngày 18 tháng 9 [năm 2026] hoặc 18 tháng 9 [năm 2026]
        d_text_match = re.search(r'(?:ngày\s+)?(\d{1,2})\s+tháng\s+(\d{1,2})(?:\s+năm\s+(\d{4}))?', lower)
        if d_text_match:
            d = int(d_text_match.group(1))
            m = int(d_text_match.group(2))
            y = int(d_text_match.group(3)) if d_text_match.group(3) else 2026
            if 1 <= d <= 31 and 1 <= m <= 12:
                return f"{y:04d}-{m:02d}-{d:02d}"

        # 2. Định dạng: YYYY-MM-DD
        d_iso = re.search(r'\b(202\d-\d{2}-\d{2})\b', message)
        if d_iso:
            return d_iso.group(1)

        # 3. Định dạng: DD/MM[/YYYY] hoặc DD-MM[-YYYY]
        d_slash = re.search(r'\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{4}))?\b', message)
        if d_slash:
            d = int(d_slash.group(1))
            m = int(d_slash.group(2))
            y = int(d_slash.group(3)) if d_slash.group(3) else 2026
            if 1 <= d <= 31 and 1 <= m <= 12:
                return f"{y:04d}-{m:02d}-{d:02d}"

        return None
        
    def _clean_json_output(self, text: str) -> str:
        """
        Bóc tách chuỗi JSON thô từ output của LLM.
        """
        cleaned = text.strip()
        json_match = re.search(r'```json\s*(.*?)\s*```', cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(1).strip()
        else:
            # Phòng hờ markdown code block không có nhãn json
            json_match_alt = re.search(r'```\s*(.*?)\s*```', cleaned, re.DOTALL)
            if json_match_alt:
                cleaned = json_match_alt.group(1).strip()
        return cleaned

    def _fast_extract_intent_and_params(self, message: str, name_to_id: Dict[str, str], today_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Nhận diện Ý định (Intent) và trích xuất thực thể bằng phương pháp Fast Rule-Based/Heuristic.
        Tốc độ thực thi < 1ms, không cần gọi Ollama LLM, giúp chatbot phản hồi ngay lập tức.
        Nếu không khớp mẫu rõ ràng nào, trả về None để Fallback sang LLM.
        """
        lower_msg = message.lower().strip()
        if today_date is None:
            today_date = self._get_today_date()

        # 1. Tìm mã nhân viên nếu có trong tin nhắn
        detected_eid = None
        for code_key in sorted(name_to_id.keys(), key=len, reverse=True):
            if re.search(r'\b' + re.escape(code_key) + r'\b', lower_msg):
                detected_eid = name_to_id[code_key]
                break

        # 2. Bắt khoảng ngày "từ ... đến ..."
        date_range_match = re.search(r'từ\s+(?:ngày\s+)?(\d{1,2}[/-]\d{1,2}(?:[/-]\d{4})?|\d{4}-\d{2}-\d{2})\s+đến\s+(?:ngày\s+)?(\d{1,2}[/-]\d{1,2}(?:[/-]\d{4})?|\d{4}-\d{2}-\d{2})', message, re.IGNORECASE)
        from_date = None
        to_date = None
        if date_range_match:
            def parse_d(raw_d):
                raw_d = raw_d.strip()
                if "-" in raw_d and len(raw_d) == 10:
                    return raw_d
                parts = re.split(r'[/-]', raw_d)
                if len(parts) == 2:
                    return f"2026-{int(parts[1]):02d}-{int(parts[0]):02d}"
                elif len(parts) == 3:
                    if len(parts[0]) == 4:
                        return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                    return f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
                return raw_d
            from_date = parse_d(date_range_match.group(1))
            to_date = parse_d(date_range_match.group(2))

        # 3. Fast match: Yêu cầu xuất file Excel
        if re.search(r'(?:xuất|tải|export|xin|lấy|gửi|cho xin|tạo|download)\s+(?:file|tập tin|báo cáo|dữ liệu)?\s*(?:excel|xlsx)|file\s*excel|\bexcel\b|\bxlsx\b', lower_msg):
            slash_match = re.search(r'(?:tháng\s*)?(\d{1,2})[/-](\d{4})', message, re.IGNORECASE)
            month_match = re.search(r'tháng\s+(\d+)', message, re.IGNORECASE)
            year_match = re.search(r'năm\s+(\d{4})', message, re.IGNORECASE)
            m = int(slash_match.group(1)) if slash_match else (int(month_match.group(1)) if month_match else 8)
            y = int(slash_match.group(2)) if slash_match else (int(year_match.group(1)) if year_match else 2026)
            return {
                "intent": "export_monthly_excel",
                "employee_id": None,
                "from_date": None,
                "to_date": None,
                "date": None,
                "filter_status": None,
                "month": m,
                "year": y,
                "reason": "Fast Match: export_monthly_excel"
            }

        # 4. Fast match: Chấm công theo ngày (ai đi làm / ai vắng / hôm nay / ngày cụ thể)
        has_range = bool(re.search(r'\btừ\s+(?:ngày\s+)?.*?đến\b', lower_msg)) or "lịch sử" in lower_msg
        parsed_date = self._parse_date_from_message(message, today_date)
        has_att_keywords = bool(re.search(r'(đi làm|có mặt|vắng|nghỉ|trễ|muộn|đúng giờ|chấm công|ai vắng|ai đi làm|ai có mặt|ai nghỉ|ai trễ|nhân viên vắng|nhân viên đi làm|nhân viên có mặt|tình hình chấm công)', lower_msg))

        is_daily_att = (not has_range) and (
            (parsed_date is not None and has_att_keywords) or
            bool(re.search(r'(ai đi làm|ai vắng mặt|ai vắng|ai nghỉ|ai có mặt|ai trễ|ai muộn|nhân viên nào vắng|nhân viên nào đi làm|nhân viên nào có mặt)', lower_msg)) or
            bool(re.search(r'danh sách\s+(?:các\s+)?nhân viên\s+(?:đi làm|có mặt|vắng|nghỉ|trễ|muộn|đúng giờ)', lower_msg))
        )
        if is_daily_att:
            d_val = parsed_date if parsed_date else today_date
            if re.search(r'(vắng|nghỉ)', lower_msg):
                f_status = "absent"
            elif re.search(r'(đi làm|có mặt|đúng giờ)', lower_msg):
                f_status = "present"
            elif re.search(r'(trễ|muộn)', lower_msg):
                f_status = "late"
            else:
                f_status = "all"

            return {
                "intent": "daily_attendance",
                "employee_id": None,
                "from_date": None,
                "to_date": None,
                "date": d_val,
                "filter_status": f_status,
                "month": None,
                "year": None,
                "reason": "Fast Match: daily_attendance"
            }

        # 5. Fast match: Danh sách nhân viên (Chỉ khi KHÔNG hỏi về trạng thái chấm công / đi làm / vắng)
        if not has_att_keywords and re.search(r'(danh sách nhân viên|danh sách các nhân viên|danh bạ nhân viên|nhân viên trong công ty|công ty có những nhân viên nào|danh sách nhân sự|tất cả nhân viên|có bao nhiêu nhân viên|xem nhân viên|các nhân viên)', lower_msg):
            return {
                "intent": "employee_list",
                "employee_id": None,
                "from_date": None,
                "to_date": None,
                "date": None,
                "filter_status": None,
                "month": None,
                "year": None,
                "reason": "Fast Match: employee_list"
            }

        # 6. Fast match: Thống kê tháng
        if re.search(r'(thống kê|báo cáo|tổng quan).*(chuyên cần|chấm công).*tháng|thống kê.*tháng|chuyên cần.*tháng', lower_msg):
            slash_match = re.search(r'(?:tháng\s*)?(\d{1,2})[/-](\d{4})', message, re.IGNORECASE)
            month_match = re.search(r'tháng\s+(\d+)', message, re.IGNORECASE)
            year_match = re.search(r'năm\s+(\d{4})', message, re.IGNORECASE)
            m = int(slash_match.group(1)) if slash_match else (int(month_match.group(1)) if month_match else 8)
            y = int(slash_match.group(2)) if slash_match else (int(year_match.group(1)) if year_match else 2026)
            return {
                "intent": "monthly_attendance_statistics",
                "employee_id": None,
                "from_date": None,
                "to_date": None,
                "date": None,
                "filter_status": None,
                "month": m,
                "year": y,
                "reason": "Fast Match: monthly_attendance_statistics"
            }

        # 7. Fast match: Lịch sử chấm công theo khoảng ngày
        if (from_date and to_date) or ("lịch sử" in lower_msg and detected_eid):
            return {
                "intent": "attendance_history",
                "employee_id": detected_eid,
                "from_date": from_date or "2026-08-01",
                "to_date": to_date or today_date,
                "date": None,
                "filter_status": None,
                "month": None,
                "year": None,
                "reason": "Fast Match: attendance_history"
            }

        # 8. Fast match: Chuyên cần nhân viên cụ thể
        if detected_eid and re.search(r'(chuyên cần|chấm công|đi làm|đi trễ|đi muộn|vắng|nghỉ|đúng giờ|mấy lần|bao nhiêu|thông tin)', lower_msg):
            return {
                "intent": "employee_attendance",
                "employee_id": detected_eid,
                "from_date": None,
                "to_date": None,
                "date": None,
                "filter_status": None,
                "month": None,
                "year": None,
                "reason": "Fast Match: employee_attendance"
            }

        # 9. Fast match: Lời chào / Câu hỏi ngoài lề
        if re.search(r'^(chào|xin chào|hello|hi|bạn là ai|thời tiết|chúc|cảm ơn|thank)', lower_msg):
            return {
                "intent": "unrelated",
                "employee_id": None,
                "from_date": None,
                "to_date": None,
                "date": None,
                "filter_status": None,
                "month": None,
                "year": None,
                "reason": "Fast Match: greeting / unrelated"
            }

        return None

    def _extract_intent_and_params(self, message: str) -> Dict[str, Any]:
        """
        Sử dụng cơ chế Fast Path kết hợp Fallback sang LLM để nhận diện Intent và trích xuất các tham số.
        """
        today_date = self._get_today_date()
        current_date_str = today_date  # Bối cảnh hiện tại: ngày hôm nay thực tế
        
        # Tự động nạp danh bạ nhân viên thực tế từ Repository
        name_to_id = {}
        sample_emp_lines = []
        try:
            from integrations.my_enterprise_attendance.repository import get_repository
            repo_emps = get_repository().get_employee_list().get("employees", [])
            for e in repo_emps:
                e_code = str(e.get("employee_id") or e.get("employee_code") or "").strip()
                e_name = str(e.get("name") or "").strip()
                if e_code:
                    name_to_id[e_code.lower()] = e_code
                    name_to_id[f"nhân viên {e_code.lower()}"] = e_code
                    name_to_id[f"mã {e_code.lower()}"] = e_code
                if e_code and e_name:
                    name_to_id[e_name.lower()] = e_code
                    parts = e_name.split()
                    if parts:
                        first_n = parts[-1].lower()
                        name_to_id[f"nhân viên {first_n}"] = e_code
            for e in repo_emps[:5]:
                ec = e.get("employee_id")
                en = e.get("name")
                if ec and en:
                    sample_emp_lines.append(f"- '{en}' hoặc mã '{ec}' -> employee_id = '{ec}'")
        except Exception:
            pass

        # 1. FAST PATH: Thử phân tích siêu tốc (< 1ms) không qua LLM
        fast_parsed = self._fast_extract_intent_and_params(message, name_to_id, today_date=today_date)
        if fast_parsed is not None:
            parsed_data = fast_parsed
        else:
            # 2. SLOW PATH: Gọi LLM nếu câu hỏi phức tạp / không khớp rule
            samples_text = "\n".join(sample_emp_lines) if sample_emp_lines else "- Mã nhân viên là mã số thực tế (ví dụ: '009', '000001', '010', '001')"

            prompt = (
                "Bạn là một hệ thống phân tích ý định (Intent Classifier) và trích xuất thực thể (Entity Extractor) chuyên sâu cho hệ thống quản lý chuyên cần và chấm công nhân sự TAS.\n"
                "Nhiệm vụ của bạn là đọc tin nhắn người dùng và trả về một JSON duy nhất biểu diễn ý định và các tham số tương ứng.\n\n"
                "DANH SÁCH CÁC INTENT HỖ TRỢ:\n"
                "1. `employee_attendance` (Xem thông tin chuyên cần, tóm tắt đi làm, đi muộn, vắng mặt của 1 nhân viên cụ thể):\n"
                "   - Ví dụ: 'Xem thông tin chuyên cần nhân viên 009', 'Nhân viên 001 đi trễ bao nhiêu lần?', 'Nhân viên Vy đi làm bao nhiêu ngày?'.\n"
                "   - Yêu cầu tham số: `employee_id` (BẮT BUỘC, ví dụ: '009', '000001', '010', '001').\n"
                "2. `attendance_history` (Xem lịch sử chấm công chi tiết theo khoảng thời gian của 1 nhân viên cụ thể):\n"
                "   - Ví dụ: 'Lịch sử chấm công của nhân viên 009 từ 2026-08-01 đến 2026-08-15'.\n"
                "   - Yêu cầu tham số: `employee_id`, `from_date` (YYYY-MM-DD), `to_date` (YYYY-MM-DD).\n"
                "3. `monthly_attendance_statistics` (Xem thống kê chuyên cần/chấm công của tất cả nhân viên hoặc theo tháng/năm toàn công ty):\n"
                "   - Ví dụ: 'Thống kê chuyên cần tháng 8 năm 2026'.\n"
                "   - Yêu cầu tham số: `month` (số nguyên từ 1 đến 12), `year` (số nguyên, ví dụ: 2026).\n"
                "4. `employee_list` (Xem danh sách hoặc danh bạ toàn bộ nhân viên trong công ty):\n"
                "   - Ví dụ: 'Xem danh sách nhân viên', 'Danh bạ nhân viên', 'Công ty có những nhân viên nào?'.\n"
                "   - Không yêu cầu tham số bắt buộc.\n"
                "   - LƯU Ý QUAN TRỌNG: Nếu câu hỏi có từ khóa về trạng thái đi làm, có mặt, vắng mặt, đi muộn (như 'danh sách nhân viên đi làm', 'nhân viên có mặt ngày 18 tháng 9',...) thì đó là `daily_attendance`, TUYỆT ĐỐI KHÔNG chọn `employee_list`.\n"
                "5. `daily_attendance` (Xem tình hình chấm công của toàn bộ nhân viên trong ngày hôm nay hoặc theo ngày cụ thể - ai đi làm, ai vắng mặt, ai đi muộn):\n"
                "   - Ví dụ: 'Xem danh sách các nhân viên vắng mặt hôm nay', 'Xem nhân viên đi làm hôm nay', 'Xem danh sách nhân viên đi làm ngày 18 tháng 9', 'Ai đi làm hôm nay?', 'Ai vắng mặt ngày 19/08/2026?'.\n"
                "   - Tham số: `date` (YYYY-MM-DD hoặc 'hôm nay'), `filter_status` ('absent', 'present', 'late', 'all').\n"
                "6. `unrelated` (Câu hỏi hoàn toàn không liên quan đến chuyên cần, chấm công, nhân sự của công ty).\n\n"
                "Mã nhân viên trong hệ thống là mã số thực tế (codeDisplay):\n"
                f"{samples_text}\n\n"
                "Quy tắc trích xuất tham số:\n"
                "- Nếu người dùng nhắc tới ngày cụ thể hoặc khoảng thời gian, hãy chuyển đổi nó về định dạng YYYY-MM-DD (ví dụ: 'từ ngày 01/08/2026 đến 15/08/2026' -> from_date='2026-08-01', to_date='2026-08-15').\n"
                "- GIỮ NGUYÊN ĐỊNH DẠNG MÃ NHÂN VIÊN khi người dùng cung cấp (ví dụ: '001', '007', '009', '010', '000001').\n"
                "- Với các câu hỏi chung cho toàn công ty như 'Ai vắng mặt ngày 19/08/2026?', intent BẮT BUỘC là 'daily_attendance', KHÔNG trích xuất năm '2026' thành mã nhân viên '026', và employee_id BẮT BUỘC là null.\n"
                f"- Nếu người dùng hỏi 'hôm nay', hãy đặt `date` = '{today_date}' (theo ngày thực tế hôm nay).\n"
                "- Nếu thiếu năm, mặc định là năm 2026 (dựa theo bối cảnh).\n"
                "- Nếu hỏi thống kê tháng nhưng không chỉ rõ năm, mặc định là năm 2026.\n"
                "- Nếu người dùng nhắc đến mã nhân viên (ví dụ: '009', '000001', '010', '001') hoặc tên nhân viên, hãy điền employee_id tương ứng.\n"
                "- Nếu không tìm thấy mã hoặc tên nhân viên trong danh bạ, hãy đặt `employee_id` là null (để Agent hỏi lại).\n\n"
                "Định dạng JSON đầu ra bắt buộc (CHỈ trả về duy nhất chuỗi JSON, không giải thích gì thêm):\n"
                "{\n"
                '  "intent": "tên_intent_hoặc_unrelated",\n'
                '  "employee_id": "mã_nhân_viên_hoặc_null",\n'
                '  "from_date": "YYYY-MM-DD_hoặc_null",\n'
                '  "to_date": "YYYY-MM-DD_hoặc_null",\n'
                '  "date": "YYYY-MM-DD_hoặc_null",\n'
                '  "filter_status": "absent_hoặc_present_hoặc_late_hoặc_all_hoặc_null",\n'
                '  "month": số_nguyên_hoặc_null,\n'
                '  "year": số_nguyên_hoặc_null,\n'
                '  "reason": "lý do ngắn gọn phân loại"\n'
                "}\n\n"
                f"Câu hỏi của người dùng: \"{message}\"\n"
                "JSON phản hồi:"
            )
            
            try:
                raw_response = ""
                # Ưu tiên 1: Thử shared.llm của team nếu có cấu hình
                if LLMFactory is not None and load_config is not None:
                    try:
                        cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared", "llm", "config.yaml")
                        if os.path.exists(cfg_path):
                            config = load_config(cfg_path)
                            llm = LLMFactory.create(config)
                            resp = llm.generate(LLMRequest(
                                messages=[{"role": "user", "content": prompt}],
                                temperature=0.1
                            ))
                            if resp and resp.content:
                                raw_response = resp.content.strip()
                    except Exception:
                        pass

                # Ưu tiên 2: Thử core.llm (LangChain Ollama) nếu khả dụng
                if not raw_response and get_chat_model is not None:
                    try:
                        llm = get_chat_model(temperature=0.1)
                        raw_response = llm.invoke(prompt).content.strip()
                    except Exception:
                        pass

                if raw_response:
                    cleaned_json = self._clean_json_output(raw_response)
                    parsed_data = json.loads(cleaned_json)
                else:
                    parsed_data = {
                        "intent": "unrelated",
                        "employee_id": None,
                        "from_date": None,
                        "to_date": None,
                        "month": None,
                        "year": None,
                        "reason": "Fallback regex mode"
                    }
            except Exception:
                parsed_data = {
                    "intent": "unrelated",
                    "employee_id": None,
                    "from_date": None,
                    "to_date": None,
                    "month": None,
                    "year": None,
                    "reason": "Fallback error"
                }

        # Hậu xử lý tăng cường độ chính xác cho mô hình nhỏ (Small LLM Guardrail)
        lower_msg = message.lower()

        # Ưu tiên trích xuất trực tiếp mã nhân viên nếu khớp trong danh bạ
        for code_key in sorted(name_to_id.keys(), key=len, reverse=True):
            if re.search(r'\b' + re.escape(code_key) + r'\b', lower_msg):
                parsed_data["employee_id"] = name_to_id[code_key]
                break

        # Trích xuất khoảng ngày dạng YYYY-MM-DD hoặc DD/MM/YYYY
        date_range_match = re.search(r'từ\s+(?:ngày\s+)?(\d{1,2}[/-]\d{1,2}(?:[/-]\d{4})?|\d{4}-\d{2}-\d{2})\s+đến\s+(?:ngày\s+)?(\d{1,2}[/-]\d{1,2}(?:[/-]\d{4})?|\d{4}-\d{2}-\d{2})', message, re.IGNORECASE)
        if date_range_match:
            def parse_d(raw_d):
                raw_d = raw_d.strip()
                if "-" in raw_d and len(raw_d) == 10:
                    return raw_d
                parts = re.split(r'[/-]', raw_d)
                if len(parts) == 2:
                    return f"2026-{int(parts[1]):02d}-{int(parts[0]):02d}"
                elif len(parts) == 3:
                    if len(parts[0]) == 4:
                        return f"{parts[0]}-{int(parts[1]):02d}-{int(parts[2]):02d}"
                    return f"{parts[2]}-{int(parts[1]):02d}-{int(parts[0]):02d}"
                return raw_d

            parsed_data["from_date"] = parse_d(date_range_match.group(1))
            parsed_data["to_date"] = parse_d(date_range_match.group(2))
            parsed_data["intent"] = "attendance_history"

        # 1. Ánh xạ mã NV nếu còn thiếu hoặc kiểm tra trực tiếp
        if not parsed_data.get("employee_id") or str(parsed_data.get("employee_id")).strip().lower() in ("null", "none", ""):
            # Tra cứu chính xác theo pattern
            for n_pattern, eid in name_to_id.items():
                if n_pattern in lower_msg:
                    parsed_data["employee_id"] = eid
                    break
        else:
            # Guardrail: Nếu LLM tự suy đoán mã nhân viên dù tin nhắn người dùng không hề đề cập mã hay tên nhân viên
            current_eid = str(parsed_data.get("employee_id", "")).strip().upper()
            if current_eid in set(name_to_id.values()):
                has_explicit_id = bool(re.search(rf'\b{re.escape(current_eid)}\b', message, re.IGNORECASE))
                has_name = any(n in lower_msg for n, eid in name_to_id.items() if eid.upper() == current_eid)
                if not has_explicit_id and not has_name:
                    parsed_data["employee_id"] = None

        if str(parsed_data.get("employee_id", "")).strip().lower() in ("null", "none", ""):
            parsed_data["employee_id"] = None

        # 2. Khôi phục intent nếu bị phân loại nhầm là unrelated hoặc phân loại chính xác tính năng mới
        # A. Nhận diện chấm công theo ngày (hôm nay hoặc ngày cụ thể) của toàn công ty TRƯỚC (loại trừ nếu hỏi khoảng ngày hoặc lịch sử)
        has_range = bool(re.search(r'\btừ\s+(?:ngày\s+)?.*?đến\b', lower_msg)) or "lịch sử" in lower_msg
        parsed_date = self._parse_date_from_message(message, today_date)
        has_att_keywords = bool(re.search(r'(đi làm|có mặt|vắng|nghỉ|trễ|muộn|đúng giờ|chấm công|ai vắng|ai đi làm|ai có mặt|ai nghỉ|ai trễ|nhân viên vắng|nhân viên đi làm|nhân viên có mặt|tình hình chấm công)', lower_msg))

        is_daily_att = (not has_range) and (
            (parsed_date is not None and has_att_keywords) or
            bool(re.search(r'(ai đi làm|ai vắng mặt|ai vắng|ai nghỉ|ai có mặt|ai trễ|ai muộn|nhân viên nào vắng|nhân viên nào đi làm|nhân viên nào có mặt)', lower_msg)) or
            bool(re.search(r'danh sách\s+(?:các\s+)?nhân viên\s+(?:đi làm|có mặt|vắng|nghỉ|trễ|muộn|đúng giờ)', lower_msg))
        )

        if is_daily_att:
            parsed_data["intent"] = "daily_attendance"
            parsed_data["employee_id"] = None
            parsed_data["from_date"] = None
            parsed_data["to_date"] = None
            parsed_data["date"] = parsed_date if parsed_date else today_date

            if re.search(r'(vắng|nghỉ)', lower_msg):
                parsed_data["filter_status"] = "absent"
            elif re.search(r'(đi làm|có mặt|đúng giờ)', lower_msg):
                parsed_data["filter_status"] = "present"
            elif re.search(r'(trễ|muộn)', lower_msg):
                parsed_data["filter_status"] = "late"
            else:
                parsed_data["filter_status"] = "all"

        # B. Nhận diện danh sách nhân viên (Chỉ khi KHÔNG hỏi về trạng thái chấm công / đi làm / vắng)
        elif not has_att_keywords and re.search(r'(danh sách nhân viên|danh sách các nhân viên|danh bạ nhân viên|nhân viên trong công ty|công ty có những nhân viên nào|danh sách nhân sự|tất cả nhân viên|có bao nhiêu nhân viên|xem nhân viên|các nhân viên)', lower_msg):
            parsed_data["intent"] = "employee_list"

        # C. Nhận diện yêu cầu xuất file Excel thống kê chuyên cần
        if re.search(r'(?:xuất|tải|export|xin|lấy|gửi|cho xin|tạo|download)\s+(?:file|tập tin|báo cáo|dữ liệu)?\s*(?:excel|xlsx)|file\s*excel|\bexcel\b|\bxlsx\b', lower_msg):
            parsed_data["intent"] = "export_monthly_excel"
            slash_match = re.search(r'(?:tháng\s*)?(\d{1,2})[/-](\d{4})', message, re.IGNORECASE)
            month_match = re.search(r'tháng\s+(\d+)', message, re.IGNORECASE)
            year_match = re.search(r'năm\s+(\d{4})', message, re.IGNORECASE)
            if slash_match:
                parsed_data["month"] = int(slash_match.group(1))
                parsed_data["year"] = int(slash_match.group(2))
            else:
                if month_match:
                    parsed_data["month"] = int(month_match.group(1))
                if year_match:
                    parsed_data["year"] = int(year_match.group(1))

        elif parsed_data.get("intent") == "unrelated":
            if parsed_data.get("employee_id"):
                if re.search(r'(đi trễ|đi muộn|vắng|nghỉ phép|đi làm|chuyên cần|chấm công|check-in|checkin|có mặt|bao nhiêu ngày|mấy ngày|mấy lần)', lower_msg):
                    parsed_data["intent"] = "employee_attendance"

        return parsed_data

    def _detect_query_target(self, question: str) -> str:
        """
        Xác định trọng tâm cụ thể của câu hỏi người dùng khi tra cứu thông tin chuyên cần:
        - 'late': Đi trễ / đi muộn
        - 'absence': Vắng mặt / nghỉ phép / không phép
        - 'work_days': Số ngày làm việc / ngày công
        - 'on_time': Đi làm đúng giờ
        - 'general': Tra cứu hồ sơ/thông tin chuyên cần tổng quan
        """
        q = question.lower().strip()
        # 1. Đi trễ / đi muộn
        if re.search(r'\b(trễ|muộn)\b', q) or "đi trễ" in q or "đi muộn" in q:
            return "late"

        # 2. Vắng mặt / nghỉ phép / không check-in
        if re.search(r'\b(vắng|nghỉ|phép)\b', q) or "vắng mặt" in q or "nghỉ phép" in q or "không check" in q or "chưa check" in q:
            return "absence"

        # 3. Ngày công / ngày đi làm
        if re.search(r'(đi làm|ngày công|làm việc|số công)', q) and re.search(r'(bao nhiêu|mấy|tổng|được)', q):
            return "work_days"

        # 4. Đúng giờ
        if "đúng giờ" in q and re.search(r'(bao nhiêu|mấy|có|không|tỷ lệ)', q):
            return "on_time"

        # Mặc định là câu hỏi thông tin chuyên cần tổng quan
        return "general"

    def _format_attendance_text(self, text: str) -> str:
        """
        Hậu xử lý định dạng văn bản để đảm bảo ngắt dòng rõ ràng,
        không bị dính chùm dòng và chuẩn hóa thuật ngữ:
        - Có duyệt -> Vắng có phép
        - Không duyệt -> Vắng không phép
        """
        cleaned = text.strip()
        
        # 0. Loại bỏ tiền tố mẫu rò rỉ nếu có (ví dụ: 'Mẫu cho Xem thông tin...', 'Ví dụ mẫu...')
        cleaned = re.sub(r'^(Mẫu cho|Ví dụ mẫu|Mẫu)\s+.*?:(\n|\r\n)*', '', cleaned, flags=re.IGNORECASE).strip()

        # 1. Loại bỏ chữ ký email hoặc placeholder dạng [Tên của bạn]
        cleaned = re.sub(r'(\n|\r\n)*(Trân trọng|Thân ái),?\s*(\n|\r\n)*(\[.*?\])?\s*$', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\[Tên\s*(của\s*)?bạn\]', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\[(Mã|Họ và tên|Họ tên|Tên|Chức vụ|Phòng ban|X|Giờ|Ngày|from_date|to_date)\]\s*', '', cleaned)

        # 2. Chuẩn hóa thuật ngữ trạng thái nghỉ/vắng
        cleaned = re.sub(r'Số ngày nghỉ phép(\s+có\s+duyệt)?:', 'Số ngày vắng có phép:', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'ngày nghỉ phép(\s+có\s+duyệt)?', 'ngày vắng có phép', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'Nghỉ phép có duyệt', 'Vắng có phép', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'Vắng mặt không phép', 'Vắng không phép', cleaned, flags=re.IGNORECASE)

        # 2.5. Chuyển đổi triệt để các từ/ký tự tiếng Trung rò rỉ từ mô hình LLM (như Qwen) sang tiếng Việt
        chinese_translations = [
            (r'(\d+)\s*小时\s*(\d+)\s*分钟', r'\1 giờ \2 phút'),
            (r'(\d+)\s*小时', r'\1 giờ'),
            (r'(\d+)\s*分钟', r'\1 phút'),
            (r'(\d+)\s*秒', r'\1 giây'),
            (r'(\d+)\s*天', r'\1 ngày'),
            (r'小时', 'giờ'),
            (r'分钟', 'phút'),
            (r'秒', 'giây'),
            (r'迟到', 'đi muộn'),
            (r'缺勤', 'vắng mặt'),
            (r'旷工', 'vắng không phép'),
            (r'请假', 'vắng có phép'),
            (r'出勤', 'đi làm'),
            (r'准时', 'đúng giờ'),
            (r'打卡', 'chấm công'),
            (r'签到', 'Check-in'),
            (r'签退', 'Check-out'),
            (r'正常', 'bình thường'),
            (r'异常', 'bất thường'),
        ]
        for c_pat, v_repl in chinese_translations:
            cleaned = re.sub(c_pat, v_repl, cleaned)

        # 3. Đảm bảo các bullet point (- hoặc +) dính liền sau câu được ngắt dòng, không ngắt dấu nối bên trong ngoặc đơn như (010 - Công ty)
        bullet_lines = []
        for line in cleaned.splitlines():
            in_paren = 0
            new_chars = []
            i = 0
            while i < len(line):
                ch = line[i]
                if ch == '(':
                    in_paren += 1
                elif ch == ')':
                    in_paren = max(0, in_paren - 1)
                
                if in_paren == 0 and i > 0 and (line[i:i+3] in (' - ', ' + ') or (line[i:i+2] in ('- ', '+ ') and line[i-1] in '.:;!?')):
                    new_chars.append('\n')
                    if line[i] == ' ':
                        i += 1
                new_chars.append(line[i])
                i += 1
            bullet_lines.append(''.join(new_chars))
        cleaned = '\n'.join(bullet_lines)

        # 4. Đảm bảo trước các tiêu đề phân mục lớn có 2 dấu xuống dòng (\n\n)
        headers = [
            "Thông tin về nhân viên",
            "Tổng quan toàn công ty:",
            "Chi tiết theo từng nhân viên:",
            "Thống kê tổng quan:",
            "Chi tiết từng ngày:",
            "Chi tiết các lần đi muộn:",
            "Chi tiết các ngày vắng:",
            "Chi tiết các ngày không check-in có mặt đi làm:",
            "Chi tiết các ngày vắng có phép / không phép:",
            "Chi tiết các ngày vắng mặt / không check-in:",
            "Danh sách chi tiết lịch sử chấm công gần đây:",
            "Danh sách chi tiết:",
            "Danh sách chấm công gần đây:",
            "Danh sách nhân viên công ty",
            "Tình hình vắng mặt",
            "Danh sách nhân viên vắng mặt",
            "Danh sách nhân viên đi làm",
            "Báo cáo chấm công",
            "Nhận xét:"
        ]
        for h in headers:
            cleaned = re.sub(rf'([^\n])\s*({re.escape(h)})', r'\1\n\n\2', cleaned, flags=re.IGNORECASE)

        # 5. Chuẩn hóa khoảng trống thừa: tối đa 2 dấu xuống dòng liên tiếp
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
        return cleaned

    def _fallback_format_employee_list(self, tool_data: Dict[str, Any]) -> str:
        """Định dạng dự phòng danh sách nhân viên khi LLM gặp sự cố."""
        emps = tool_data.get("employees", [])
        total = tool_data.get("total_employees", len(emps))
        lines = [f"Danh sách nhân viên công ty (Tổng số: {total} nhân viên):\n"]
        for idx, e in enumerate(emps, 1):
            eid = e.get("employee_id", "")
            name = e.get("name", "")
            pos = e.get("position", "Nhân viên")
            dept = e.get("department", "")
            lines.append(f"{idx}. {eid}: {name} - Chức vụ: {pos} ({dept})")
        lines.append(f"\nNhận xét: Hệ thống hiện ghi nhận và quản lý thông tin của {total} nhân sự trên.")
        return "\n".join(lines)

    def _fallback_format_daily_attendance(self, tool_data: Dict[str, Any], question: str) -> str:
        """Định dạng dự phòng báo cáo chấm công theo ngày khi LLM gặp sự cố."""
        date_str = tool_data.get("date", "")
        summary = tool_data.get("summary", {})
        working = tool_data.get("working_employees", [])
        absent = tool_data.get("absent_employees", [])
        q = question.lower()
        latest_data_date = self._get_system_latest_date()
        latest_note = f"\n\n💡 Ghi chú: Dữ liệu chấm công gần nhất ghi nhận trong hệ thống là ngày {latest_data_date}." if latest_data_date and latest_data_date != date_str else ""

        if any(k in q for k in ["vắng", "nghỉ"]):
            if not absent:
                on_time = summary.get("present_on_time", sum(1 for w in working if w.get("status") == "Present"))
                late = summary.get("late", sum(1 for w in working if w.get("status") == "Late"))
                unrecorded = summary.get("unrecorded", 0)
                work_detail = f"{len(working)} nhân viên (trong đó {on_time} đúng giờ, {late} đi muộn)"
                unrec_note = f"\n- Ngoài ra, có {unrecorded} nhân sự chưa ghi nhận bản ghi chấm công trong ngày." if unrecorded > 0 else ""
                return (
                    f"Tình hình vắng mặt ngày {date_str}:\n\n"
                    f"- Theo dữ liệu hệ thống ghi nhận, ngày {date_str} không có nhân viên nào ghi nhận vắng mặt chính thức (0 vắng có phép, 0 vắng không phép).\n"
                    f"- Tổng số nhân viên có mặt làm việc: {work_detail}.{unrec_note}{latest_note}"
                )
            lines = [f"Danh sách nhân viên vắng mặt ngày {date_str} (Tổng số: {len(absent)} nhân viên vắng):\n"]
            for a in absent:
                eid = a.get("employee_id", "")
                name = a.get("name", "")
                dept = a.get("department", "")
                st = "Vắng có phép" if a.get("status") == "Leave_Approved" else "Vắng không phép"
                note = f" ({a.get('notes')})" if a.get("notes") else ""
                lines.append(f"- {eid}: {name} ({dept}) - Trạng thái: {st}{note}")
            lines.append(f"\nNhận xét: Có {summary.get('leave_approved', 0)} nhân sự vắng có phép và {summary.get('absent_unexcused', 0)} nhân sự vắng không phép.")
            return "\n".join(lines)

        if any(k in q for k in ["đi làm", "có mặt"]):
            if not working:
                total_emps = summary.get("total_employees", 36)
                latest_hint = f"\n\n💡 Gợi ý: Dữ liệu chấm công gần nhất được ghi nhận trong hệ thống là ngày {latest_data_date}. Bạn có thể hỏi 'Xem nhân viên đi làm ngày {latest_data_date}' để tra cứu." if latest_data_date and latest_data_date != date_str else ""
                return (
                    f"Danh sách nhân viên đi làm ngày {date_str} (Tổng số: 0 nhân viên có mặt):\n\n"
                    f"- Theo dữ liệu hệ thống ghi nhận, ngày {date_str} hiện chưa có nhân viên nào có bản ghi chấm công (0 nhân viên có mặt).\n"
                    f"- Toàn bộ {total_emps} nhân sự trong công ty hiện chưa phát sinh dữ liệu đi làm trong ngày {date_str}.\n\n"
                    f"Nhận xét: Hiện chưa có dữ liệu chấm công cho ngày {date_str}.{latest_hint}"
                )
            lines = [f"Danh sách nhân viên đi làm ngày {date_str} (Tổng số: {len(working)} nhân viên có mặt):\n"]
            for w in working:
                eid = w.get("employee_id", "")
                name = w.get("name", "")
                dept = w.get("department", "")
                st = "Đúng giờ" if w.get("status") == "Present" else "Đi muộn"
                ci = w.get("check_in") or "Chưa có"
                co = w.get("check_out") or "Chưa có"
                lines.append(f"- {eid}: {name} ({dept}) - {st} (Check-in: {ci}, Check-out: {co})")
            lines.append(f"\nNhận xét: Toàn bộ {len(working)} nhân sự đã có mặt làm việc trong ngày {date_str}.")
            return "\n".join(lines)

        return (
            f"Báo cáo chấm công ngày {date_str}:\n\n"
            f"Tổng quan toàn công ty:\n"
            f"- Tổng số nhân viên: {summary.get('total_employees', 0)}\n"
            f"- Đi làm: {summary.get('total_working', 0)} (Đúng giờ: {summary.get('present_on_time', 0)}, Đi muộn: {summary.get('late', 0)})\n"
            f"- Vắng mặt: {summary.get('total_absent', 0)} (Vắng có phép: {summary.get('leave_approved', 0)}, Vắng không phép: {summary.get('absent_unexcused', 0)})\n"
            f"- Chưa ghi nhận: {summary.get('unrecorded', 0)}{latest_note}"
        )

    def _format_monthly_attendance_statistics(self, tool_data: Dict[str, Any]) -> str:
        """Định dạng trực tiếp báo cáo thống kê chuyên cần tháng của toàn công ty."""
        month_int = tool_data.get("month", 8)
        year_int = tool_data.get("year", 2026)
        c_summary = tool_data.get("company_summary", {})
        emp_details = tool_data.get("employee_details", {})

        tot_rec = c_summary.get("total_records", 0)
        if tot_rec == 0 or not emp_details:
            return (
                f"Báo cáo thống kê chuyên cần tháng {month_int} năm {year_int}:\n\n"
                f"Tổng quan toàn công ty:\n"
                f"- Tổng số lượt chấm công: 0 lượt\n"
                f"- Đúng giờ: 0 lượt\n"
                f"- Đi muộn: 0 lượt\n"
                f"- Vắng có phép: 0 lượt\n"
                f"- Vắng không phép: 0 lượt\n\n"
                f"Nhận xét: Hệ thống chưa ghi nhận dữ liệu chấm công nào trong tháng {month_int}/{year_int}."
            )

        pres = c_summary.get("present", 0)
        late = c_summary.get("late", 0)
        lv_app = c_summary.get("leave_approved", 0)
        abs_un = c_summary.get("absent_unexcused", 0)

        remarks = []
        if pres > 0:
            remarks.append(f"{pres} lượt đi làm đúng giờ")
        if late > 0:
            remarks.append(f"{late} lượt đi muộn")
        if lv_app > 0:
            remarks.append(f"{lv_app} ngày vắng có phép")
        if abs_un > 0:
            remarks.append(f"{abs_un} ngày vắng không phép")

        remark_detail = ", ".join(remarks) if remarks else "chưa có phát sinh lượt chấm công"
        rate = round((pres / tot_rec) * 100, 1) if tot_rec > 0 else 0

        return (
            f"Báo cáo thống kê chuyên cần tháng {month_int} năm {year_int}:\n\n"
            f"Tổng quan toàn công ty:\n"
            f"- Tổng số lượt chấm công: {tot_rec} lượt\n"
            f"- Đúng giờ: {pres} lượt\n"
            f"- Đi muộn: {late} lượt\n"
            f"- Vắng có phép: {lv_app} lượt\n"
            f"- Vắng không phép: {abs_un} lượt\n\n"
            f"Nhận xét: Toàn công ty trong tháng {month_int}/{year_int} có {remark_detail} (tỷ lệ đúng giờ đạt {rate}%).\n\n"
            f"💡 Gợi ý: Bạn có thể yêu cầu \"Xuất file Excel thống kê tháng {month_int}/{year_int}\" để tải về danh sách chi tiết đầy đủ của từng nhân viên."
        )

    def _format_attendance_history(self, tool_data: Dict[str, Any]) -> str:
        """Định dạng trực tiếp lịch sử chấm công theo khoảng ngày của nhân viên."""
        emp = tool_data.get("employee", {})
        name = emp.get("name") or emp.get("employee_name", "N/A")
        eid = emp.get("employee_id") or emp.get("employee_code", "")
        from_d = tool_data.get("from_date", "")
        to_d = tool_data.get("to_date", "")
        summary = tool_data.get("summary", {})
        records = tool_data.get("records", [])

        tot = summary.get("total_days", len(records))
        pres = summary.get("present", 0)
        late = summary.get("late", 0)
        lv = summary.get("leave_approved", 0)
        abs_un = summary.get("absent_unexcused", 0)

        lines = [
            f"Từ ngày {from_d} đến {to_d}, nhân viên {eid} ({name}) có lịch sử chấm công như sau:\n",
            f"Tổng số ngày: {tot}",
            f"- Số ngày đúng giờ: {pres}",
            f"- Số lần đi muộn: {late} lần",
            f"- Số ngày vắng có phép: {lv}",
            f"- Số ngày vắng không phép: {abs_un}\n",
            "Chi tiết từng ngày:"
        ]
        for r in records:
            d = r.get("date", "")
            st = r.get("status", "")
            ci = r.get("check_in") or "Chưa có"
            co = r.get("check_out") or "Chưa có"
            note = f" ({r.get('notes')})" if r.get("notes") else ""
            if st == "Present":
                desc = f"Đúng giờ (Check-in: {ci}, Check-out: {co})"
            elif st == "Late":
                late_m = r.get("late_minutes", 0)
                desc = f"Đi muộn {late_m} phút (Check-in: {ci}, Check-out: {co})"
            elif st == "Leave_Approved":
                desc = f"Vắng có phép{note}"
            elif st == "Absent_Unexcused":
                desc = f"Vắng không phép{note}"
            else:
                desc = f"{st} (Check-in: {ci}, Check-out: {co})"
            lines.append(f"- {d}: {desc}")

        remarks = []
        if pres > 0:
            remarks.append(f"{pres} ngày đúng giờ")
        if late > 0:
            remarks.append(f"{late} lần đi muộn")
        if lv > 0:
            remarks.append(f"{lv} ngày vắng có phép")
        if abs_un > 0:
            remarks.append(f"{abs_un} ngày vắng không phép")
        rem_text = ", ".join(remarks) if remarks else "chưa có bản ghi chấm công"
        lines.append(f"\nNhận xét: Nhân viên {name} có {rem_text} trong khoảng thời gian này.")
        return "\n".join(lines)

    def _format_employee_attendance_late(self, tool_data: Dict[str, Any]) -> str:
        """Định dạng trực tiếp câu trả lời chuyên sâu về đi trễ / đi muộn."""
        emp = tool_data.get("employee", {})
        name = emp.get("name") or emp.get("employee_name", "N/A")
        eid = emp.get("employee_id") or emp.get("employee_code", "")
        summary = tool_data.get("summary", {})
        late_records = tool_data.get("late_records", [])
        tot_days = summary.get("total_days_tracked", 0)
        late_count = summary.get("late", len(late_records))

        if late_count == 0:
            return (
                f"Theo dữ liệu hệ thống ghi nhận, nhân viên {name} ({eid}) không đi trễ lần nào (0 lần) trong tổng số {tot_days} ngày theo dõi.\n\n"
                f"Nhận xét: Nhân viên {name} luôn đi làm đúng giờ (tỷ lệ đúng giờ đạt 100%)."
            )

        lines = [
            f"Theo dữ liệu hệ thống ghi nhận, nhân viên {name} ({eid}) đã đi trễ {late_count} lần trong tổng số {tot_days} ngày theo dõi.\n",
            "Chi tiết các lần đi muộn:"
        ]
        for r in late_records:
            d = r.get("date", "")
            m = r.get("late_minutes", 0)
            ci = r.get("check_in") or "Chưa có"
            co = r.get("check_out") or "Chưa có"
            lines.append(f"- {d}: Đi muộn {m} phút (Check-in: {ci}, Check-out: {co})")

        lines.append(f"\nNhận xét: Nhân viên {name} có {late_count} lần đi muộn trong thời gian theo dõi.")
        return "\n".join(lines)

    def _format_employee_attendance_absence(self, tool_data: Dict[str, Any]) -> str:
        """Định dạng trực tiếp câu trả lời chuyên sâu về vắng mặt / không check-in / nghỉ phép."""
        emp = tool_data.get("employee", {})
        name = emp.get("name") or emp.get("employee_name", "N/A")
        eid = emp.get("employee_id") or emp.get("employee_code", "")
        summary = tool_data.get("summary", {})
        leave_records = tool_data.get("leave_records", [])
        tot_days = summary.get("total_days_tracked", 0)
        tot_sys = summary.get("total_system_days", tot_days)
        tot_worked = summary.get("total_days_worked", 0)
        days_no_ci = summary.get("days_without_checkin", 0)
        unrecorded_dates = summary.get("unrecorded_dates", tool_data.get("unrecorded_dates", []))
        lv = summary.get("leave_approved", 0)
        abs_un = summary.get("absent_unexcused", 0)

        if lv == 0 and abs_un == 0 and days_no_ci == 0:
            return (
                f"Theo dữ liệu hệ thống ghi nhận, nhân viên {name} ({eid}) không có ngày vắng nào "
                f"(0 ngày vắng có phép, 0 ngày vắng không phép, 0 ngày không check-in) trong tổng số {tot_sys} ngày làm việc theo dõi.\n\n"
                f"Nhận xét: Nhân viên {name} có mặt làm việc đầy đủ tất cả các ngày, đạt tỷ lệ chuyên cần tuyệt đối."
            )

        lines = []
        if days_no_ci > 0:
            lines.append(
                f"Theo dữ liệu hệ thống ghi nhận, nhân viên {name} ({eid}) có {days_no_ci} ngày không check-in có mặt đi làm "
                f"(trong đó: {lv} ngày vắng có phép, {abs_un} ngày vắng không phép) trên tổng số {tot_sys} ngày làm việc của hệ thống "
                f"(đã đi làm {tot_worked}/{tot_sys} ngày).\n"
            )
        else:
            lines.append(
                f"Theo dữ liệu hệ thống ghi nhận, nhân viên {name} ({eid}) có {lv} ngày vắng có phép và {abs_un} ngày vắng không phép "
                f"trong tổng số {tot_days} ngày theo dõi.\n"
            )

        if leave_records:
            lines.append("Chi tiết các ngày vắng có phép / không phép:")
            for r in leave_records:
                d = r.get("date", "")
                st = "Vắng có phép" if r.get("status") == "Leave_Approved" else "Vắng không phép"
                note = f" ({r.get('notes')})" if r.get("notes") else ""
                lines.append(f"- {d}: {st}{note}")
            lines.append("")

        if unrecorded_dates:
            lines.append(f"Chi tiết {len(unrecorded_dates)} ngày không check-in có mặt đi làm:")
            for d in unrecorded_dates:
                lines.append(f"- {d}: Không có dữ liệu check-in có mặt")
            lines.append("")

        if days_no_ci > 0:
            leave_part = f", {lv} ngày vắng có phép và {abs_un} ngày vắng không phép" if (lv > 0 or abs_un > 0) else ""
            lines.append(f"Nhận xét: Nhân viên {name} có {days_no_ci} ngày không check-in có mặt đi làm{leave_part} trong thời gian theo dõi.")
        else:
            lines.append(f"Nhận xét: Nhân viên {name} có {lv} ngày vắng có phép và {abs_un} ngày vắng không phép trong thời gian theo dõi.")

        return "\n".join(lines)

    def _format_employee_attendance_work_days(self, tool_data: Dict[str, Any]) -> str:
        """Định dạng trực tiếp câu trả lời chuyên sâu về ngày công làm việc."""
        emp = tool_data.get("employee", {})
        name = emp.get("name") or emp.get("employee_name", "N/A")
        eid = emp.get("employee_id") or emp.get("employee_code", "")
        summary = tool_data.get("summary", {})
        tot_tracked = summary.get("total_days_tracked", 0)
        tot_worked = summary.get("total_days_worked", 0)
        pres = summary.get("present", 0)
        late = summary.get("late", 0)
        lv = summary.get("leave_approved", 0)
        leave_note = f" (ngoài ra có {lv} ngày vắng có phép)" if lv > 0 else ""

        return (
            f"Theo dữ liệu hệ thống ghi nhận, nhân viên {name} ({eid}) đã đi làm tổng cộng {tot_worked} ngày (trong đó {pres} ngày đúng giờ, {late} lần đi muộn) trên tổng số {tot_tracked} ngày theo dõi{leave_note}.\n\n"
            f"Nhận xét: Nhân viên {name} hoàn thành {tot_worked}/{tot_tracked} ngày công trong thời gian theo dõi."
        )

    def _format_employee_attendance_on_time(self, tool_data: Dict[str, Any]) -> str:
        """Định dạng trực tiếp câu trả lời chuyên sâu về đi làm đúng giờ."""
        emp = tool_data.get("employee", {})
        name = emp.get("name") or emp.get("employee_name", "N/A")
        eid = emp.get("employee_id") or emp.get("employee_code", "")
        summary = tool_data.get("summary", {})
        tot_tracked = summary.get("total_days_tracked", 0)
        pres = summary.get("present", 0)
        rate = round((pres / tot_tracked) * 100, 1) if tot_tracked > 0 else 0

        return (
            f"Theo dữ liệu hệ thống ghi nhận, nhân viên {name} ({eid}) đã đi làm đúng giờ {pres} ngày trên tổng số {tot_tracked} ngày theo dõi (đạt tỷ lệ đúng giờ {rate}%).\n\n"
            f"Nhận xét: Nhân viên {name} có {pres} ngày đi làm đúng giờ."
        )

    def _format_employee_attendance_general(self, tool_data: Dict[str, Any]) -> str:
        """Định dạng trực tiếp thông tin chuyên cần tổng quan chuẩn mực cho 1 nhân viên."""
        emp = tool_data.get("employee", {})
        name = emp.get("name") or emp.get("employee_name", "N/A")
        eid = emp.get("employee_id") or emp.get("employee_code", "")
        pos = emp.get("position", "Nhân viên")
        dept = emp.get("department", "Công ty")
        summary = tool_data.get("summary", {})
        recent = tool_data.get("recent_records", [])

        tot = summary.get("total_days_tracked", 0)
        tot_sys = summary.get("total_system_days", tot)
        days_no_ci = summary.get("days_without_checkin", 0)
        pres = summary.get("present", 0)
        late = summary.get("late", 0)
        lv = summary.get("leave_approved", 0)
        abs_un = summary.get("absent_unexcused", 0)

        lines = [
            f"Thông tin về nhân viên {eid} ({name}):",
            f"- Tên: {name}",
            f"- Chức vụ: {pos}",
            f"- Phòng ban: {dept}\n",
            "Thống kê tổng quan:",
            f"- Tổng số ngày theo dõi: {tot} ngày (toàn hệ thống: {tot_sys} ngày)",
            f"- Số ngày đúng giờ: {pres} ngày",
            f"- Số lần đi muộn: {late} lần",
            f"- Số ngày vắng có phép: {lv} ngày",
            f"- Số ngày vắng không phép: {abs_un} ngày",
            f"- Số ngày không check-in đi làm: {days_no_ci} ngày\n"
        ]

        if recent:
            lines.append("Danh sách chi tiết lịch sử chấm công gần đây:")
            for r in recent:
                d = r.get("date", "")
                st = r.get("status", "")
                ci = r.get("check_in") or "Chưa có"
                co = r.get("check_out") or "Chưa có"
                if st == "Present":
                    desc = f"Đúng giờ (Check-in: {ci}, Check-out: {co})"
                elif st == "Late":
                    m = r.get("late_minutes", 0)
                    desc = f"Đi muộn {m} phút (Check-in: {ci}, Check-out: {co})"
                elif st == "Leave_Approved":
                    note = f" - {r.get('notes')}" if r.get("notes") else ""
                    desc = f"Vắng có phép{note} (Check-in: {ci}, Check-out: {co})"
                else:
                    note = f" - {r.get('notes')}" if r.get("notes") else ""
                    desc = f"Vắng không phép{note} (Check-in: {ci}, Check-out: {co})"
                lines.append(f"- {d}: {desc}")
            lines.append("")

        remarks = []
        if pres > 0:
            remarks.append(f"{pres} ngày đúng giờ")
        if late > 0:
            remarks.append(f"{late} lần đi muộn")
        if lv > 0:
            remarks.append(f"{lv} ngày vắng có phép")
        if abs_un > 0:
            remarks.append(f"{abs_un} ngày vắng không phép")
        rem_text = ", ".join(remarks) if remarks else "chưa có bản ghi chấm công"

        lines.append(f"Nhận xét: Nhân viên {name} có {rem_text} trong lịch sử theo dõi.")
        return "\n".join(lines)

    def _synthesize_response(self, question: str, intent: str, tool_data: Dict[str, Any], chat_history_str: str) -> str:
        """
        Tổng hợp câu trả lời tự nhiên bằng tiếng Việt: Ưu tiên Fast Deterministic Formatter (< 1ms),
        tự động fallback sang Ollama LLM nếu gặp câu hỏi phức tạp / mở rộng.
        """
        # 1. Nếu kết quả từ MCP Server báo lỗi hoặc không thành công
        if not tool_data.get("success"):
            err_msg = tool_data.get("error", "Không thể lấy thông tin chuyên cần từ hệ thống.")
            return f"Thông báo: {err_msg}"

        # Xác định trọng tâm câu hỏi đối với intent employee_attendance
        query_target = self._detect_query_target(question) if intent == "employee_attendance" else "general"

        # 2. Xử lý trường hợp nhân viên tồn tại nhưng chưa có bản ghi chấm công nào (ATT-13)
        if intent == "employee_attendance" and tool_data.get("summary", {}).get("total_days_tracked", 0) == 0:
            emp = tool_data.get("employee", {})
            name = emp.get("name", "N/A")
            eid = emp.get("employee_id", "")
            pos = emp.get("position", "N/A")
            dep = emp.get("department", "N/A")
            if query_target == "late":
                return f"Hiện tại nhân viên {name} ({eid}) chưa có bản ghi chấm công nào được ghi nhận trong hệ thống (0 lần đi muộn)."
            elif query_target == "absence":
                return f"Hiện tại nhân viên {name} ({eid}) chưa có bản ghi chấm công nào được ghi nhận trong hệ thống (0 ngày vắng)."
            elif query_target == "work_days":
                return f"Hiện tại nhân viên {name} ({eid}) chưa có bản ghi chấm công nào được ghi nhận trong hệ thống (0 ngày đi làm)."
            else:
                return (
                    f"Thông tin về nhân viên {eid} ({name}):\n"
                    f"- Tên: {name}\n"
                    f"- Chức vụ: {pos}\n"
                    f"- Phòng ban: {dep}\n\n"
                    f"Thống kê tổng quan:\n"
                    f"- Tổng số ngày theo dõi: 0 ngày\n"
                    f"- Số ngày đúng giờ: 0 ngày\n"
                    f"- Số lần đi muộn: 0 lần\n"
                    f"- Số ngày vắng có phép: 0 ngày\n"
                    f"- Số ngày vắng không phép: 0 ngày\n\n"
                    f"Hiện tại nhân viên {name} ({eid}) chưa có bản ghi chấm công nào được ghi nhận trong hệ thống."
                )

        if intent == "attendance_history" and tool_data.get("summary", {}).get("total_days", 0) == 0:
            emp = tool_data.get("employee", {})
            name = emp.get("name", "N/A")
            eid = emp.get("employee_id", "")
            from_d = tool_data.get("from_date", "")
            to_d = tool_data.get("to_date", "")
            return (
                f"Từ ngày {from_d} đến {to_d}, nhân viên {eid} ({name}) chưa có bản ghi chấm công nào trong hệ thống.\n\n"
                f"Tổng số ngày: 0\n"
                f"- Số ngày đúng giờ: 0\n"
                f"- Số lần đi muộn: 0 lần\n"
                f"- Số ngày vắng có phép: 0\n"
                f"- Số ngày vắng không phép: 0"
            )

        # 3. FAST PATH: Định dạng trực tiếp với tốc độ siêu tốc (< 1ms, 0% lỗi rò rỉ ngôn ngữ)
        try:
            if intent == "employee_list":
                return self._fallback_format_employee_list(tool_data)
            elif intent == "daily_attendance":
                return self._fallback_format_daily_attendance(tool_data, question)
            elif intent == "attendance_history":
                return self._format_attendance_history(tool_data)
            elif intent == "monthly_attendance_statistics":
                return self._format_monthly_attendance_statistics(tool_data)
            elif intent == "employee_attendance":
                if query_target == "late":
                    return self._format_employee_attendance_late(tool_data)
                elif query_target == "absence":
                    return self._format_employee_attendance_absence(tool_data)
                elif query_target == "work_days":
                    return self._format_employee_attendance_work_days(tool_data)
                elif query_target == "on_time":
                    return self._format_employee_attendance_on_time(tool_data)
                else:
                    return self._format_employee_attendance_general(tool_data)
        except Exception as fast_fmt_err:
            print(f"[FAST FORMATTER] Fallback sang LLM do: {fast_fmt_err}")

        # 4. SLOW PATH: Fallback sang LLM nếu các bộ định dạng trên gặp sự cố
        if intent == "employee_list":
            return self._fallback_format_employee_list(tool_data)
        # 4. Nếu là Intent chấm công theo ngày (hỏi về vắng mặt / nghỉ)
        elif intent == "daily_attendance" and re.search(r'(vắng|nghỉ)', question.lower()):
            d_str = tool_data.get("date") or self._get_today_date()
            absent_emps = tool_data.get("absent_employees", [])
            summary = tool_data.get("summary", {})
            working_emps = tool_data.get("working_employees", [])
            working_count = summary.get("total_working", len(working_emps))
            on_time_count = summary.get("present_on_time", 0)
            late_count = summary.get("late", 0)
            unrec_count = summary.get("unrecorded", 0)

            unrec_instruction = f"- Ngoài ra, có {unrec_count} nhân sự chưa phát sinh bản ghi chấm công trong ngày." if unrec_count > 0 else ""

            prompt = (
                "Bạn là trợ lý ảo TAS chuyên trách chấm công và chuyên cần nhân sự của công ty.\n"
                f"Hãy sử dụng kết quả dữ liệu vắng mặt ngày {d_str} dưới đây để trả lời câu hỏi của người dùng một cách trực quan, chính xác và đúng trọng tâm.\n\n"
                f"Lịch sử chat gần đây (nếu có):\n{chat_history_str}\n\n"
                f"Câu hỏi của người dùng: \"{question}\"\n"
                f"Ngày truy vấn: {d_str}\n"
                f"Số nhân viên vắng mặt: {len(absent_emps)}\n"
                f"Dữ liệu danh sách vắng mặt (JSON): {json.dumps(absent_emps, ensure_ascii=False)}\n\n"
                "QUY TẮC PHẢN HỒI BẮT BUỘC:\n"
                "1. TRẢ LỜI TRỰC TIẾP VÀO CÂU HỎI:\n"
                "   - Nếu KHÔNG CÓ AI VẮNG MẶT (len = 0):\n"
                f"     + Bắt đầu bằng: 'Tình hình vắng mặt ngày {d_str}:'\n"
                f"     + Nêu rõ: '- Theo dữ liệu hệ thống ghi nhận, ngày {d_str} không có nhân viên nào ghi nhận vắng mặt chính thức (0 vắng có phép, 0 vắng không phép).'\n"
                f"     + Nêu rõ số liệu đi làm thực tế: '- Tổng số nhân viên có mặt làm việc: {working_count} nhân viên (trong đó {on_time_count} đúng giờ, {late_count} đi muộn).'\n"
                f"     + Ghi nhận thêm: '{unrec_instruction}'\n"
                "   - Nếu CÓ NHÂN VIÊN VẮNG MẶT (len > 0):\n"
                f"     + Bắt đầu bằng: 'Danh sách nhân viên vắng mặt ngày {d_str} (Tổng số: {len(absent_emps)} nhân viên vắng):'\n"
                "     + Liệt kê đầy đủ TẤT CẢ nhân viên trong danh sách JSON trên. Mỗi nhân viên một dòng riêng biệt với dấu '- '.\n"
                "     + Định dạng: - [Mã NV]: [Họ tên] ([Phòng ban]) - Trạng thái: [Vắng có phép/Vắng không phép] ([Lý do/ghi chú nếu có])\n"
                f"     + Dòng cuối cùng: 'Nhận xét: Trong ngày {d_str} có {summary.get('leave_approved', 0)} nhân sự vắng có phép và {summary.get('absent_unexcused', 0)} nhân sự vắng không phép.'\n"
                "2. CHÍNH XÁC VỀ THUẬT NGỮ:\n"
                "   - 'Leave_Approved': 'Vắng có phép'.\n"
                "   - 'Absent_Unexcused': 'Vắng không phép'.\n"
                "   - Tuyệt đối không dùng chữ ký email như 'Trân trọng, [Tên của bạn]', 'Thân ái', hoặc placeholder '[...]'.\n\n"
                "Câu trả lời của bạn:"
            )
        # 5. Nếu là Intent chấm công theo ngày (hỏi về đi làm / có mặt)
        elif intent == "daily_attendance" and re.search(r'(đi làm|có mặt|làm việc|đúng giờ)', question.lower()):
            d_str = tool_data.get("date") or self._get_today_date()
            working_emps = tool_data.get("working_employees", [])
            summary = tool_data.get("summary", {})

            # Tiền xử lý danh sách nhân sự đi làm kèm giờ check-in và check-out chuẩn xác
            formatted_list = []
            for w in working_emps:
                eid = w.get("employee_id", "")
                name = w.get("name", "")
                dept = w.get("department", "Công ty")
                st = "Đúng giờ" if w.get("status") == "Present" else "Đi muộn"
                ci = w.get("check_in") or "Chưa có"
                co = w.get("check_out") or "Chưa có"
                formatted_list.append(f"- {eid}: {name} ({dept}) - {st} (Check-in: {ci}, Check-out: {co})")
            formatted_employees_str = "\n".join(formatted_list)

            prompt = (
                "Bạn là trợ lý ảo TAS chuyên trách chấm công và chuyên cần nhân sự của công ty.\n"
                f"Hãy sử dụng danh sách nhân viên đi làm ngày {d_str} dưới đây để trả lời câu hỏi của người dùng một cách trực quan, chính xác và đúng trọng tâm.\n\n"
                f"Lịch sử chat gần đây (nếu có):\n{chat_history_str}\n\n"
                f"Câu hỏi của người dùng: \"{question}\"\n"
                f"Ngày truy vấn: {d_str}\n"
                f"Tổng số nhân viên đi làm: {len(working_emps)}\n\n"
                f"Danh sách nhân viên (đã có đầy đủ Check-in và Check-out):\n{formatted_employees_str}\n\n"
                "QUY TẮC PHẢN HỒI BẮT BUỘC:\n"
                "1. TRẢ LỜI TRỰC TIẾP VÀO CÂU HỎI:\n"
                f"   - Bắt đầu bằng: 'Danh sách nhân viên đi làm ngày {d_str} (Tổng số: {len(working_emps)} nhân viên có mặt):'\n"
                "   - Liệt kê đầy đủ TẤT CẢ các nhân viên trong danh sách trên, GIỮ NGUYÊN ĐẦY ĐỦ CẢ Check-in VÀ Check-out của từng người.\n"
                f"   - Dòng cuối cùng: 'Nhận xét: Toàn bộ {len(working_emps)} nhân sự đã có mặt làm việc trong ngày {d_str} (trong đó {summary.get('present_on_time', 0)} đúng giờ, {summary.get('late', 0)} đi muộn).'\n"
                "2. CHÍNH XÁC VỀ THUẬT NGỮ VÀ THÔNG TIN:\n"
                "   - 'Present': 'Đúng giờ'.\n"
                "   - 'Late': 'Đi muộn'.\n"
                "   - Giữ nguyên họ tên và số liệu, tuyệt đối không dùng chữ ký email như 'Trân trọng, [Tên của bạn]', 'Thân ái', hoặc placeholder '[...]'.\n\n"
                "Câu trả lời của bạn:"
            )
        # 6. Nếu là Intent chấm công theo ngày (hỏi chung tình hình)
        elif intent == "daily_attendance":
            d_str = tool_data.get("date") or self._get_today_date()
            summary = tool_data.get("summary", {})
            prompt = (
                "Bạn là trợ lý ảo TAS chuyên trách chấm công và chuyên cần nhân sự của công ty.\n"
                f"Hãy sử dụng kết quả dữ liệu chấm công ngày {d_str} dưới đây để lập báo cáo tổng quan một cách trực quan, chính xác và phân chia rõ ràng từng dòng.\n\n"
                f"Lịch sử chat gần đây (nếu có):\n{chat_history_str}\n\n"
                f"Câu hỏi của người dùng: \"{question}\"\n"
                f"Dữ liệu thực tế từ hệ thống (JSON): {json.dumps(tool_data, ensure_ascii=False)}\n\n"
                "QUY TẮC PHẢN HỒI BẮT BUỘC:\n"
                f"1. Dòng đầu tiên: 'Báo cáo chấm công ngày {d_str}:'\n"
                "2. Phân chia rõ ràng bằng gạch đầu dòng:\n"
                f"- Tổng số nhân viên: {summary.get('total_employees', 0)}\n"
                f"- Đi làm: {summary.get('total_working', 0)} (Đúng giờ: {summary.get('present_on_time', 0)}, Đi muộn: {summary.get('late', 0)})\n"
                f"- Vắng mặt: {summary.get('total_absent', 0)} (Vắng có phép: {summary.get('leave_approved', 0)}, Vắng không phép: {summary.get('absent_unexcused', 0)})\n"
                f"- Chưa ghi nhận: {summary.get('unrecorded', 0)}\n"
                "3. Tuyệt đối không dùng chữ ký email như 'Trân trọng, [Tên của bạn]', 'Thân ái', hoặc placeholder '[...]'.\n\n"
                "Câu trả lời của bạn:"
            )
        # 7. Nếu là Intent thống kê tháng của toàn công ty
        elif intent == "monthly_attendance_statistics":
            month_int = tool_data.get("month", 8)
            year_int = tool_data.get("year", 2026)
            c_summary = tool_data.get("company_summary", {})
            emp_details = tool_data.get("employee_details", {})

            tot_rec = c_summary.get("total_records", 0)
            if tot_rec == 0 or not emp_details:
                return (
                    f"Báo cáo thống kê chuyên cần tháng {month_int} năm {year_int}:\n\n"
                    f"Tổng quan toàn công ty:\n"
                    f"- Tổng số lượt chấm công: 0 lượt\n"
                    f"- Đúng giờ: 0 lượt\n"
                    f"- Đi muộn: 0 lượt\n"
                    f"- Vắng có phép: 0 lượt\n"
                    f"- Vắng không phép: 0 lượt\n\n"
                    f"Nhận xét: Hệ thống chưa ghi nhận dữ liệu chấm công nào trong tháng {month_int}/{year_int}."
                )

            pres = c_summary.get("present", 0)
            late = c_summary.get("late", 0)
            lv_app = c_summary.get("leave_approved", 0)
            abs_un = c_summary.get("absent_unexcused", 0)

            remarks = []
            if pres > 0:
                remarks.append(f"{pres} lượt đi làm đúng giờ")
            if late > 0:
                remarks.append(f"{late} lượt đi muộn")
            if lv_app > 0:
                remarks.append(f"{lv_app} ngày vắng có phép")
            if abs_un > 0:
                remarks.append(f"{abs_un} ngày vắng không phép")

            remark_detail = ", ".join(remarks) if remarks else "chưa có phát sinh lượt chấm công"
            rate = round((pres / tot_rec) * 100, 1) if tot_rec > 0 else 0

            return (
                f"Báo cáo thống kê chuyên cần tháng {month_int} năm {year_int}:\n\n"
                f"Tổng quan toàn công ty:\n"
                f"- Tổng số lượt chấm công: {tot_rec} lượt\n"
                f"- Đúng giờ: {pres} lượt\n"
                f"- Đi muộn: {late} lượt\n"
                f"- Vắng có phép: {lv_app} lượt\n"
                f"- Vắng không phép: {abs_un} lượt\n\n"
                f"Nhận xét: Toàn công ty trong tháng {month_int}/{year_int} có {remark_detail} (tỷ lệ đúng giờ đạt {rate}%).\n\n"
                f"💡 Gợi ý: Bạn có thể yêu cầu \"Xuất file Excel thống kê tháng {month_int}/{year_int}\" để tải về danh sách chi tiết đầy đủ của từng nhân viên."
            )
        elif intent == "attendance_history":
            prompt = (
                "Bạn là trợ lý ảo AI thông minh chuyên trách chuyên cần và chấm công nhân sự của công ty.\n"
                "Hãy sử dụng kết quả dữ liệu thực tế từ hệ thống chấm công dưới đây để trả lời câu hỏi của người dùng một cách trực quan, chính xác và phân chia rõ ràng từng dòng.\n\n"
                f"Lịch sử chat gần đây (nếu có):\n{chat_history_str}\n\n"
                f"Câu hỏi của người dùng: \"{question}\"\n"
                f"Intent: {intent}\n"
                f"Dữ liệu thực tế từ hệ thống (JSON): {json.dumps(tool_data, ensure_ascii=False)}\n\n"
                "QUY TẮC PHẢN HỒI BẮT BUỘC:\n"
                "1. CẤU TRÚC XUỐNG DÒNG RÕ RÀNG (BẮT BUỘC, TUYỆT ĐỐI KHÔNG VIẾT DÍNH CHÙM THÀNH 1 ĐOẠN):\n"
                "   - Mỗi khối thông tin phải cách nhau bằng MỘT DÒNG TRỐNG (2 lần xuống dòng \\n\\n).\n"
                "   - Mỗi mục con, mỗi ngày chấm công BẮT BUỘC nằm trên MỘT DÒNG RIÊNG BIỆT (dùng gạch đầu dòng - ).\n"
                "   - Khi liệt kê 'Chi tiết từng ngày': BẮT BUỘC liệt kê đầy đủ TẤT CẢ các ngày có trong danh sách 'records' của dữ liệu JSON, TUYỆT ĐỐI KHÔNG ĐƯỢC tự ý rút gọn hoặc cắt bớt.\n"
                "   - Tuyệt đối không dùng chữ ký email như 'Trân trọng, [Tên của bạn]', 'Thân ái', hoặc placeholder '[...]'.\n\n"
                "2. CHÍNH XÁC TUYỆT ĐỐI VỀ THUẬT NGỮ VÀ SỐ LIỆU:\n"
                "   - QUY TẮC NGÔN NGỮ: TUYỆT ĐỐI 100% SỬ DỤNG TIẾNG VIỆT, TUYỆT ĐỐI KHÔNG ĐƯỢC XUẤT TIẾNG TRUNG (như 小时, 分钟,...; PHẢI DÙNG 'giờ', 'phút').\n"
                "   - QUY ƯỚC THUẬT NGỮ TRẠNG THÁI (BẮT BUỘC TUÂN THỦ):\n"
                "     + 'Leave_Approved' (có duyệt): GỌI LÀ 'Vắng có phép'.\n"
                "     + 'Absent_Unexcused' (không duyệt): GỌI LÀ 'Vắng không phép'.\n"
                "     + 'Present': 'Đúng giờ'.\n"
                "     + 'Late': 'Đi muộn'.\n"
                "   - TUYỆT ĐỐI KHÔNG dùng từ 'nghỉ phép' mà PHẢI DÙNG 'Vắng có phép'.\n"
                "   - QUY TẮC LẤY SỐ LIỆU TỔNG HỢP: Lấy từ object `summary` trong JSON.\n\n"
                "3. MẪU TRÌNH BÀY CHUẨN KHI HỎI LỊCH SỬ CHUYÊN CẦN THEO KHOẢNG NGÀY:\n"
                "Từ ngày 2026-08-01 đến 2026-08-15, nhân viên 009 (Lê Hữu Thanh Vy) có lịch sử chấm công như sau:\n\n"
                "Tổng số ngày: 10\n"
                "- Số ngày đúng giờ: 7\n"
                "- Số lần đi muộn: 2 lần\n"
                "- Số ngày vắng có phép: 1\n"
                "- Số ngày vắng không phép: 0\n\n"
                "Chi tiết từng ngày:\n"
                "- 2026-08-03: Đúng giờ (Check-in: 08:15, Check-out: 17:30)\n"
                "- 2026-08-04: Đi muộn 15 phút (Check-in: 08:45, Check-out: 17:35)\n"
                "- 2026-08-05: Đúng giờ (Check-in: 08:20, Check-out: 17:30)\n"
                "- 2026-08-06: Vắng có phép (Nghỉ phép năm có lương, không có check-in)\n"
                "- 2026-08-07: Đúng giờ (Check-in: 08:10, Check-out: 17:40)\n"
                "- 2026-08-10: Đúng giờ (Check-in: 08:12, Check-out: 17:30)\n"
                "- 2026-08-11: Đúng giờ (Check-in: 08:25, Check-out: 17:45)\n"
                "- 2026-08-12: Đi muộn 5 phút (Check-in: 08:35, Check-out: 17:30)\n"
                "- 2026-08-13: Đúng giờ (Check-in: 08:15, Check-out: 17:30)\n"
                "- 2026-08-14: Đúng giờ (Check-in: 08:18, Check-out: 17:35)\n\n"
                "Nhận xét: Nhân viên Lê Hữu Thanh Vy có 7 ngày đúng giờ, 2 lần đi muộn và 1 ngày vắng có phép trong khoảng thời gian này.\n\n"
                "Câu trả lời của bạn:"
            )
        elif query_target == "late":
            emp = tool_data.get("employee", {})
            emp_name = emp.get("name") or emp.get("employee_name", "")
            emp_id = emp.get("employee_id") or emp.get("employee_code", "")
            summary = tool_data.get("summary", {})
            late_records = tool_data.get("late_records", [])

            prompt = (
                "Bạn là trợ lý ảo TAS chuyên trách chấm công và chuyên cần nhân sự của công ty.\n"
                "Hãy sử dụng kết quả dữ liệu thực tế từ hệ thống chấm công dưới đây để trả lời câu hỏi của người dùng về tình hình đi trễ / đi muộn một cách trực quan, chính xác và đúng trọng tâm.\n\n"
                f"Lịch sử chat gần đây (nếu có):\n{chat_history_str}\n\n"
                f"Câu hỏi của người dùng: \"{question}\"\n"
                f"Dữ liệu từ hệ thống:\n"
                f"- Nhân viên: {emp_name} ({emp_id})\n"
                f"- Tổng số ngày theo dõi: {summary.get('total_days_tracked', 0)} ngày\n"
                f"- Số lần đi muộn: {summary.get('late', 0)} lần\n"
                f"- Chi tiết các lần đi muộn: {json.dumps(late_records, ensure_ascii=False) if late_records else 'Không có lần đi muộn nào'}\n\n"
                "QUY TẮC PHẢN HỒI BẮT BUỘC:\n"
                "1. TRẢ LỜI TRỰC TIẾP VÀO CÂU HỎI:\n"
                "   - Dòng đầu tiên BẮT BUỘC trả lời trực tiếp số lần đi trễ/đi muộn của nhân viên trong tổng số ngày theo dõi (ví dụ: 'Theo dữ liệu hệ thống ghi nhận, nhân viên Đào Minh Thuận (010) đã đi trễ 2 lần trong tổng số 15 ngày theo dõi.').\n"
                "   - QUY TẮC NGÔN NGỮ: TUYỆT ĐỐI 100% SỬ DỤNG TIẾNG VIỆT, KHÔNG ĐƯỢC XUẤT TIẾNG TRUNG (như 小时, 分钟,...; PHẢI DÙNG 'giờ', 'phút').\n"
                "   - TUYỆT ĐỐI KHÔNG xuất thông tin chức vụ, phòng ban, hoặc bảng thống kê ngày đúng giờ/vắng phép.\n"
                "   - TUYỆT ĐỐI KHÔNG xuất danh sách lịch sử các ngày đi làm đúng giờ (người dùng chỉ hỏi về đi trễ, không hỏi lịch sử đi làm).\n"
                "   - Nếu nhân viên không đi trễ lần nào (0 lần), ghi rõ nhân viên không có lần đi muộn nào trong toàn bộ thời gian theo dõi (tỷ lệ đúng giờ đạt 100%).\n\n"
                "2. LIỆT KÊ CHI TIẾT CÁC LẦN ĐI MUỘN (NẾU CÓ):\n"
                "   - Mỗi lần đi muộn nằm trên một dòng riêng biệt, dùng gạch đầu dòng '- '.\n"
                "   - Ghi rõ ngày, số phút đi muộn, Check-in, Check-out.\n\n"
                "3. MẪU TRÌNH BÀY CHUẨN:\n\n"
                "Khi có lần đi muộn:\n"
                "Theo dữ liệu hệ thống ghi nhận, nhân viên Đào Minh Thuận (010) đã đi trễ 2 lần trong tổng số 15 ngày theo dõi.\n\n"
                "Chi tiết các lần đi muộn:\n"
                "- 2026-09-04: Đi muộn 15 phút (Check-in: 08:45, Check-out: 17:35)\n"
                "- 2026-09-12: Đi muộn 5 phút (Check-in: 08:35, Check-out: 17:30)\n\n"
                "Nhận xét: Nhân viên Đào Minh Thuận có 2 lần đi muộn trong thời gian theo dõi.\n\n"
                "Khi không có lần đi muộn nào (0 lần):\n"
                "Theo dữ liệu hệ thống ghi nhận, nhân viên Hoàng Minh An Hoàn (007) không đi trễ lần nào (0 lần) trong tổng số 15 ngày theo dõi.\n\n"
                "Nhận xét: Nhân viên Hoàng Minh An Hoàn luôn đi làm đúng giờ (tỷ lệ đúng giờ đạt 100%).\n\n"
                "Câu trả lời của bạn:"
            )
        elif query_target == "absence":
            emp = tool_data.get("employee", {})
            emp_name = emp.get("name") or emp.get("employee_name", "")
            emp_id = emp.get("employee_id") or emp.get("employee_code", "")
            summary = tool_data.get("summary", {})
            leave_records = tool_data.get("leave_records", [])
            days_no_ci = summary.get("days_without_checkin", 0)
            unrecorded_dates = summary.get("unrecorded_dates", tool_data.get("unrecorded_dates", []))
            tot_sys = summary.get("total_system_days", summary.get("total_days_tracked", 0))

            prompt = (
                "Bạn là trợ lý ảo TAS chuyên trách chấm công và chuyên cần nhân sự của công ty.\n"
                "Hãy sử dụng kết quả dữ liệu thực tế từ hệ thống chấm công dưới đây để trả lời câu hỏi của người dùng về tình hình vắng mặt / không check-in / nghỉ phép một cách trực quan, chính xác và đúng trọng tâm.\n\n"
                f"Lịch sử chat gần đây (nếu có):\n{chat_history_str}\n\n"
                f"Câu hỏi của người dùng: \"{question}\"\n"
                f"Dữ liệu từ hệ thống:\n"
                f"- Nhân viên: {emp_name} ({emp_id})\n"
                f"- Tổng số ngày làm việc của hệ thống: {tot_sys} ngày\n"
                f"- Số ngày đã đi làm: {summary.get('total_days_worked', 0)} ngày\n"
                f"- Số ngày không check-in có mặt đi làm: {days_no_ci} ngày\n"
                f"- Danh sách ngày không check-in: {', '.join(unrecorded_dates) if unrecorded_dates else 'Không có'}\n"
                f"- Số ngày vắng có phép: {summary.get('leave_approved', 0)} ngày\n"
                f"- Số ngày vắng không phép: {summary.get('absent_unexcused', 0)} ngày\n"
                f"- Chi tiết các ngày vắng có phép/không phép: {json.dumps(leave_records, ensure_ascii=False) if leave_records else 'Không có ngày vắng nào'}\n\n"
                "QUY TẮC PHẢN HỒI BẮT BUỘC:\n"
                "1. TRẢ LỜI TRỰC TIẾP VÀO CÂU HỎI:\n"
                "   - Dòng đầu tiên BẮT BUỘC trả lời trực tiếp số ngày không check-in có mặt đi làm, số ngày vắng có phép và số ngày vắng không phép của nhân viên trong tổng số ngày làm việc của hệ thống.\n"
                "   - CHÍNH XÁC VỀ THUẬT NGỮ: 'Leave_Approved' là 'Vắng có phép', 'Absent_Unexcused' là 'Vắng không phép'.\n"
                "   - TUYỆT ĐỐI KHÔNG xuất thông tin chức vụ, phòng ban, hay danh sách lịch sử các ngày đi làm đúng giờ.\n"
                "   - Nếu nhân viên không có ngày vắng hay ngày không check-in nào (0 ngày), ghi rõ nhân viên có mặt đầy đủ các ngày làm việc.\n\n"
                "2. LIỆT KÊ CHI TIẾT CÁC NGÀY KHÔNG CHECK-IN / VẮNG (NẾU CÓ):\n"
                "   - Mỗi ngày nằm trên một dòng riêng biệt, dùng gạch đầu dòng '- '.\n"
                "   - Ghi rõ ngày và tình trạng.\n\n"
                "3. MẪU TRÌNH BÀY CHUẨN:\n\n"
                "Khi có ngày không check-in / vắng:\n"
                "Theo dữ liệu hệ thống ghi nhận, nhân viên Lê Hữu Thanh Vy (009) có 9 ngày không check-in có mặt đi làm (trong đó 0 ngày vắng có phép, 0 ngày vắng không phép) trên tổng số 36 ngày làm việc của hệ thống (đã đi làm 27/36 ngày).\n\n"
                "Chi tiết các ngày không check-in có mặt đi làm:\n"
                "- 2026-09-01: Không có dữ liệu check-in có mặt\n"
                "- 2026-09-02: Không có dữ liệu check-in có mặt\n\n"
                "Nhận xét: Nhân viên Lê Hữu Thanh Vy có 9 ngày không check-in có mặt đi làm trong thời gian theo dõi.\n\n"
                "Khi không có ngày vắng nào (0 ngày):\n"
                "Theo dữ liệu hệ thống ghi nhận, nhân viên Hoàng Minh An Hoàn (007) không có ngày vắng nào (0 ngày vắng có phép, 0 ngày vắng không phép, 0 ngày không check-in) trong tổng số 36 ngày theo dõi.\n\n"
                "Nhận xét: Nhân viên Hoàng Minh An Hoàn đạt tỷ lệ chuyên cần tuyệt đối.\n\n"
                "Câu trả lời của bạn:"
            )
        elif query_target == "work_days":
            emp = tool_data.get("employee", {})
            emp_name = emp.get("name") or emp.get("employee_name", "")
            emp_id = emp.get("employee_id") or emp.get("employee_code", "")
            summary = tool_data.get("summary", {})

            prompt = (
                "Bạn là trợ lý ảo TAS chuyên trách chấm công và chuyên cần nhân sự của công ty.\n"
                "Hãy sử dụng kết quả dữ liệu thực tế từ hệ thống chấm công dưới đây để trả lời câu hỏi của người dùng về số ngày làm việc / ngày công một cách trực quan, chính xác và đúng trọng tâm.\n\n"
                f"Lịch sử chat gần đây (nếu có):\n{chat_history_str}\n\n"
                f"Câu hỏi của người dùng: \"{question}\"\n"
                f"Dữ liệu từ hệ thống:\n"
                f"- Nhân viên: {emp_name} ({emp_id})\n"
                f"- Tổng số ngày theo dõi: {summary.get('total_days_tracked', 0)} ngày\n"
                f"- Tổng số ngày đi làm: {summary.get('total_days_worked', 0)} ngày\n"
                f"- Đúng giờ: {summary.get('present', 0)} ngày\n"
                f"- Đi muộn: {summary.get('late', 0)} lần\n"
                f"- Vắng có phép: {summary.get('leave_approved', 0)} ngày\n"
                f"- Vắng không phép: {summary.get('absent_unexcused', 0)} ngày\n\n"
                "QUY TẮC PHẢN HỒI BẮT BUỘC:\n"
                "1. TRẢ LỜI TRỰC TIẾP VÀO CÂU HỎI:\n"
                "   - Dòng đầu tiên BẮT BUỘC trả lời trực tiếp tổng số ngày đi làm của nhân viên trên tổng số ngày theo dõi.\n"
                "   - Nêu rõ trong đó có bao nhiêu ngày đúng giờ và bao nhiêu lần đi muộn (nếu có).\n"
                "   - TUYỆT ĐỐI KHÔNG xuất thông tin chức vụ, phòng ban, hay danh sách check-in từng ngày.\n\n"
                "2. MẪU TRÌNH BÀY CHUẨN:\n"
                "Theo dữ liệu hệ thống ghi nhận, nhân viên Lê Thị Trà My (001) đã đi làm tổng cộng 13 ngày (trong đó 11 ngày đúng giờ, 2 lần đi muộn) trên tổng số 15 ngày theo dõi (ngoài ra có 2 ngày vắng có phép).\n\n"
                "Nhận xét: Nhân viên Lê Thị Trà My hoàn thành 13/15 ngày công trong thời gian theo dõi.\n\n"
                "Câu trả lời của bạn:"
            )
        elif query_target == "on_time":
            emp = tool_data.get("employee", {})
            emp_name = emp.get("name") or emp.get("employee_name", "")
            emp_id = emp.get("employee_id") or emp.get("employee_code", "")
            summary = tool_data.get("summary", {})

            prompt = (
                "Bạn là trợ lý ảo TAS chuyên trách chấm công và chuyên cần nhân sự của công ty.\n"
                "Hãy sử dụng kết quả dữ liệu thực tế từ hệ thống chấm công dưới đây để trả lời câu hỏi của người dùng về tình hình đi làm đúng giờ một cách trực quan, chính xác và đúng trọng tâm.\n\n"
                f"Lịch sử chat gần đây (nếu có):\n{chat_history_str}\n\n"
                f"Câu hỏi của người dùng: \"{question}\"\n"
                f"Dữ liệu từ hệ thống:\n"
                f"- Nhân viên: {emp_name} ({emp_id})\n"
                f"- Tổng số ngày theo dõi: {summary.get('total_days_tracked', 0)} ngày\n"
                f"- Số ngày đúng giờ: {summary.get('present', 0)} ngày\n"
                f"- Số lần đi muộn: {summary.get('late', 0)} lần\n\n"
                "QUY TẮC PHẢN HỒI BẮT BUỘC:\n"
                "1. TRẢ LỜI TRỰC TIẾP VÀO CÂU HỎI:\n"
                "   - Dòng đầu tiên BẮT BUỘC trả lời trực tiếp số ngày đi làm đúng giờ của nhân viên trên tổng số ngày theo dõi.\n"
                "   - TUYỆT ĐỐI KHÔNG xuất thông tin chức vụ, phòng ban, hay danh sách check-in từng ngày.\n\n"
                "2. MẪU TRÌNH BÀY CHUẨN:\n"
                "Theo dữ liệu hệ thống ghi nhận, nhân viên Hoàng Minh An Hoàn (007) đã đi làm đúng giờ 15 ngày trên tổng số 15 ngày theo dõi (đạt tỷ lệ đúng giờ 100%).\n\n"
                "Nhận xét: Nhân viên Hoàng Minh An Hoàn luôn đi làm đúng giờ và đạt tỷ lệ chuyên cần tuyệt đối.\n\n"
                "Câu trả lời của bạn:"
            )
        else:
            # query_target == "general": Mẫu thông tin chuyên cần tổng quan đầy đủ
            prompt = (
                "Bạn là trợ lý ảo AI thông minh chuyên trách chuyên cần và chấm công nhân sự của công ty.\n"
                "Hãy sử dụng kết quả dữ liệu thực tế từ hệ thống chấm công dưới đây để trả lời câu hỏi của người dùng một cách trực quan, chính xác và phân chia rõ ràng từng dòng.\n\n"
                f"Lịch sử chat gần đây (nếu có):\n{chat_history_str}\n\n"
                f"Câu hỏi của người dùng: \"{question}\"\n"
                f"Intent: {intent}\n"
                f"Dữ liệu thực tế từ hệ thống (JSON): {json.dumps(tool_data, ensure_ascii=False)}\n\n"
                "QUY TẮC PHẢN HỒI BẮT BUỘC:\n"
                "1. CẤU TRÚC XUỐNG DÒNG RÕ RÀNG (BẮT BUỘC, TUYỆT ĐỐI KHÔNG VIẾT DÍNH CHÙM THÀNH 1 ĐOẠN):\n"
                "   - Mỗi khối thông tin phải cách nhau bằng MỘT DÒNG TRỐNG (2 lần xuống dòng \\n\\n).\n"
                "   - Mỗi mục con, mỗi ngày chấm công BẮT BUỘC nằm trên MỘT DÒNG RIÊNG BIỆT (dùng gạch đầu dòng - ).\n"
                "   - Khi liệt kê 'Chi tiết từng ngày': BẮT BUỘC liệt kê đầy đủ TẤT CẢ các ngày có trong danh sách 'records' của dữ liệu JSON, TUYỆT ĐỐI KHÔNG ĐƯỢC tự ý rút gọn hoặc cắt bớt.\n"
                "   - Tuyệt đối không dùng chữ ký email như 'Trân trọng, [Tên của bạn]', 'Thân ái', hoặc placeholder '[...]'.\n\n"
                "2. CHÍNH XÁC TUYỆT ĐỐI VỀ THUẬT NGỮ VÀ SỐ LIỆU:\n"
                "   - QUY TẮC NGÔN NGỮ: TUYỆT ĐỐI 100% SỬ DỤNG TIẾNG VIỆT, KHÔNG ĐƯỢC XUẤT TIẾNG TRUNG (như 小时, 分钟,...; PHẢI DÙNG 'giờ', 'phút').\n"
                "   - QUY ƯỚC THUẬT NGỮ TRẠNG THÁI (BẮT BUỘC TUÂN THỦ):\n"
                "     + 'Leave_Approved' (có duyệt): GỌI LÀ 'Vắng có phép'.\n"
                "     + 'Absent_Unexcused' (không duyệt): GỌI LÀ 'Vắng không phép'.\n"
                "     + 'Present': 'Đúng giờ'.\n"
                "     + 'Late': 'Đi muộn'.\n"
                "   - TUYỆT ĐỐI KHÔNG dùng từ 'nghỉ phép' mà PHẢI DÙNG 'Vắng có phép'.\n"
                "   - TUYỆT ĐỐI KHÔNG nhầm lẫn giữa 'Vắng có phép' và 'Vắng không phép'.\n"
                "   - QUY TẮC LẤY SỐ LIỆU TỔNG HỢP: BẮT BUỘC lấy từ object `summary` trong JSON (`total_days_worked`, `late`, `present`, `total_days_tracked`), TUYỆT ĐỐI KHÔNG đếm thủ công từ danh sách `recent_records` (vì recent_records chỉ là danh sách 5 ngày gần nhất).\n\n"
                "3. MẪU TRÌNH BÀY CHUẨN (BẮT BUỘC BẮT ĐẦU TRỰC TIẾP, TUYỆT ĐỐI KHÔNG VIẾT DÒNG 'MẪU CHO...'):\n"
                "   - BẮT BUỘC bắt đầu trực tiếp bằng 'Thông tin về nhân viên [Mã] ([Tên]):'.\n"
                "   - TUYỆT ĐỐI KHÔNG mở đầu bằng các câu như 'Mẫu cho...', 'Dưới đây là mẫu...', 'Ví dụ...'.\n\n"
                "Dưới đây là nội dung chuẩn mẫu khi trả lời thông tin chuyên cần nhân viên 009:\n"
                "Thông tin về nhân viên 009 (Lê Hữu Thanh Vy):\n"
                "- Tên: Lê Hữu Thanh Vy\n"
                "- Chức vụ: Nhân viên\n"
                "- Phòng ban: Công ty\n\n"
                "Thống kê tổng quan:\n"
                "- Tổng số ngày theo dõi: 15 ngày\n"
                "- Số ngày đúng giờ: 12 ngày\n"
                "- Số lần đi muộn: 2 lần\n"
                "- Số ngày vắng có phép: 0 ngày\n"
                "- Số ngày vắng không phép: 1 ngày\n\n"
                "Danh sách chi tiết lịch sử chấm công gần đây:\n"
                "- 2026-08-21: Đúng giờ (Check-in: 08:15, Check-out: 17:30)\n"
                "- 2026-08-20: Đi muộn 12 phút (Check-in: 08:42, Check-out: 17:30)\n"
                "- 2026-08-19: Đúng giờ (Check-in: 08:08, Check-out: 17:30)\n"
                "- 2026-08-18: Đúng giờ (Check-in: 08:14, Check-out: 17:30)\n"
                "- 2026-08-17: Đúng giờ (Check-in: 08:24, Check-out: 17:30)\n\n"
                "Nhận xét: Nhân viên Lê Hữu Thanh Vy có 12 ngày đúng giờ, 2 lần đi muộn và 1 ngày vắng không phép trong lịch sử theo dõi. Nhân viên không có ngày vắng có phép nào.\n\n"
                "4. Nếu dữ liệu báo thất bại (`success=False`), hãy giải thích lịch sự, rõ ràng lý do cho người dùng.\n\n"
                "Câu trả lời của bạn:"
            )
        
        raw_answer = ""
        try:
            # Ưu tiên 1: Thử shared.llm của team nếu có cấu hình
            if LLMFactory is not None and load_config is not None:
                try:
                    cfg_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "shared", "llm", "config.yaml")
                    if os.path.exists(cfg_path):
                        config = load_config(cfg_path)
                        llm = LLMFactory.create(config)
                        resp = llm.generate(LLMRequest(
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.0
                        ))
                        if resp and resp.content:
                            raw_answer = resp.content.strip()
                except Exception:
                    pass

            # Ưu tiên 2: Thử core.llm (LangChain Ollama) nếu khả dụng
            if not raw_answer and get_chat_model is not None:
                try:
                    llm = get_chat_model(temperature=0.0)
                    raw_answer = llm.invoke(prompt).content.strip()
                except Exception:
                    pass

            if raw_answer:
                return self._format_attendance_text(raw_answer)
        except Exception:
            pass

        if intent == "employee_list":
            return self._fallback_format_employee_list(tool_data)
        elif intent == "daily_attendance":
            return self._fallback_format_daily_attendance(tool_data, question)
        return self._fallback_format_employee_attendance(tool_data) if intent == "employee_attendance" else f"Xin lỗi, tôi đã lấy được dữ liệu chuyên cần nhưng gặp lỗi khi biên soạn câu trả lời."

    def handle(self, request: AgentRequest) -> AgentResponse:
        """
        Hàm xử lý chính của AttendanceAgent, tuân thủ contract BaseAgent.
        """
        # Bước 1: Nhận diện intent và tham số bằng LLM
        analysis = self._extract_intent_and_params(request.message)
        intent = analysis.get("intent", "unrelated")
        intent_str = str(intent).lower().strip()
        
        # Chuẩn hóa intent để bắt chuẩn các biến thể mà LLM sinh ra
        if intent == "export_monthly_excel" or "excel" in intent_str or "export" in intent_str:
            intent = "export_monthly_excel"
        elif intent == "daily_attendance" or "daily" in intent_str or "today" in intent_str:
            intent = "daily_attendance"
        elif intent == "employee_list" or "list" in intent_str or "directory" in intent_str:
            intent = "employee_list"
        elif intent == "monthly_attendance_statistics" or "month" in intent_str or "statistic" in intent_str:
            intent = "monthly_attendance_statistics"
        elif intent == "attendance_history" or "history" in intent_str or (analysis.get("from_date") and analysis.get("to_date") and analysis.get("employee_id")):
            intent = "attendance_history"
        elif intent == "employee_attendance" or ("employee" in intent_str and ("attendance" in intent_str or "late" in intent_str or "check" in intent_str)):
            intent = "employee_attendance"
        
        # Lấy lịch sử hội thoại nếu có conversation_id để phục vụ ngữ cảnh
        history_str = ""
        if request.conversation_id and get_session_history is not None:
            try:
                hist = get_session_history(request.conversation_id)
                history_str = "\n".join([f"{'User' if m.type == 'human' else 'AI'}: {m.content}" for m in hist.messages[-4:]])
            except Exception:
                pass
                
        # Bước 2: Xử lý các case không liên quan hoặc thiếu tham số
        if intent == "unrelated":
            msg = (
                "Tôi là trợ lý AI TAS chuyên trách Chuyên cần & Chấm công của công ty.\n\n"
                "Hiện tại tôi hỗ trợ các chức năng chính:\n"
                "1. Tra cứu danh sách nhân viên công ty (ví dụ: 'Xem danh sách nhân viên', 'Công ty có những nhân viên nào?')\n"
                "2. Tra cứu chấm công theo ngày / hôm nay (ví dụ: 'Xem nhân viên đi làm hôm nay', 'Danh sách nhân viên vắng mặt hôm nay')\n"
                "3. Xem thông tin chuyên cần nhân viên (ví dụ: 'Xem chuyên cần của nhân viên 009', 'Nhân viên 001 đi trễ mấy lần?')\n"
                "4. Xem lịch sử chuyên cần theo khoảng ngày (ví dụ: 'Xem lịch sử chuyên cần của 009 từ 01/08/2026 đến 15/08/2026')\n"
                "5. Xem báo cáo thống kê chuyên cần hàng tháng (ví dụ: 'Thống kê chuyên cần tháng 8 năm 2026')\n"
                "6. Xuất file Excel thống kê chuyên cần có đầy đủ chi tiết nhân viên (ví dụ: 'Xuất file Excel thống kê tháng 7 năm 2026')\n\n"
                "Vui lòng đặt câu hỏi liên quan để tôi có thể hỗ trợ bạn tốt nhất!"
            )
            return AgentResponse(
                success=True,
                data=msg,
                metadata={"intent": intent, "extracted_params": analysis}
            )

        # Xử lý Intent Xuất file Excel Thống kê chuyên cần theo tháng
        if intent == "export_monthly_excel":
            from integrations.my_enterprise_attendance.excel_exporter import export_monthly_attendance_to_excel

            slash_match = re.search(r'(?:tháng\s*)?(\d{1,2})[/-](\d{4})', request.message, re.IGNORECASE)
            month_match = re.search(r'tháng\s+(\d+)', request.message, re.IGNORECASE)
            year_match = re.search(r'năm\s+(\d{4})', request.message, re.IGNORECASE)

            month = None
            year = None
            if slash_match:
                month = int(slash_match.group(1))
                year = int(slash_match.group(2))
            else:
                if month_match:
                    month = int(month_match.group(1))
                elif analysis.get("month") and str(analysis.get("month")).strip().lower() not in ("null", "none", ""):
                    try:
                        month = int(float(analysis.get("month")))
                    except (ValueError, TypeError):
                        pass

                if year_match:
                    year = int(year_match.group(1))
                elif analysis.get("year") and str(analysis.get("year")).strip().lower() not in ("null", "none", ""):
                    try:
                        year = int(float(analysis.get("year")))
                    except (ValueError, TypeError):
                        pass

            # Tra cứu từ lịch sử nếu câu hỏi hiện tại không chỉ rõ tháng/năm
            if not month and history_str:
                m_hist = re.search(r'tháng\s*(\d{1,2})', history_str, re.IGNORECASE)
                if m_hist:
                    month = int(m_hist.group(1))
            if not year and history_str:
                y_hist = re.search(r'năm\s*(\d{4})', history_str, re.IGNORECASE)
                if y_hist:
                    year = int(y_hist.group(1))

            # Mặc định an toàn
            if not month:
                month = 7 if " 7" in f" {request.message} " else 8
            if not year:
                year = 2026

            # Validation tháng và năm
            if month < 1 or month > 12:
                return AgentResponse(
                    success=True,
                    data=f"Tháng {month} không hợp lệ. Vui lòng cung cấp tháng trong khoảng từ 1 đến 12 để xuất file Excel.",
                    metadata={"intent": intent, "extracted_params": {"month": month, "year": year}}
                )
            if year < 2000 or year > 2030:
                return AgentResponse(
                    success=True,
                    data=f"Năm {year} không hợp lệ. Vui lòng cung cấp năm trong khoảng từ 2000 đến 2030 để xuất file Excel.",
                    metadata={"intent": intent, "extracted_params": {"month": month, "year": year}}
                )

            res = export_monthly_attendance_to_excel(month, year)
            if not res.get("success"):
                err = res.get("error") or res.get("message") or "Không có dữ liệu chấm công cho tháng yêu cầu."
                return AgentResponse(
                    success=True,
                    data=f"Không thể xuất file Excel: {err}",
                    metadata={"intent": intent, "export_result": res}
                )

            fn = res.get("filename")
            t_rec = res.get("total_records", 0)
            t_emp = res.get("total_employees", 0)
            download_url = f"/api/export/{fn}"

            ans = (
                f"Đã xuất thành công file Excel thống kê chuyên cần tháng {month} năm {year} với đầy đủ chi tiết từng nhân viên!\n\n"
                f"Tổng quan dữ liệu trong file:\n"
                f"- Tổng số lượt chấm công: {t_rec} lượt\n"
                f"- Số nhân sự được thống kê chi tiết: {t_emp} nhân viên\n"
                f"- Bao gồm 3 sheet: Tổng Quan, Chi Tiết Nhân Viên và Nhật Ký Chấm Công.\n\n"
                f"👉 Tải file về máy tại: [Tải file Excel Thống Kê Tháng {month}/{year}]({download_url})"
            )
            return AgentResponse(
                success=True,
                data=ans,
                metadata={"intent": intent, "export_result": res, "download_url": download_url}
            )

        # Xác định và validate tham số cụ thể cho từng Use Case
        arguments = {}
        tool_name = ""
        
        if intent == "attendance_history":
            employee_id = analysis.get("employee_id")
            from_date = analysis.get("from_date")
            to_date = analysis.get("to_date")
            
            # Validation
            if not employee_id or str(employee_id).strip().lower() in ("null", "none", ""):
                return AgentResponse(
                    success=True,
                    data="Vui lòng cung cấp mã nhân viên (ví dụ: E001) để tôi tra cứu lịch sử chuyên cần.",
                    metadata={"intent": intent, "extracted_params": analysis}
                )
            employee_id = str(employee_id).strip().upper()
            
            if not from_date or str(from_date).strip().lower() in ("null", "none", ""):
                # Mặc định từ đầu tháng 8
                from_date = "2026-08-01"
            else:
                from_date = str(from_date).strip()

            if not to_date or str(to_date).strip().lower() in ("null", "none", ""):
                # Mặc định đến ngày hôm nay
                to_date = self._get_today_date()
            else:
                to_date = str(to_date).strip()
                
            # Kiểm tra logic ngày bắt đầu <= ngày kết thúc
            try:
                start_dt = datetime.strptime(from_date, "%Y-%m-%d")
                end_dt = datetime.strptime(to_date, "%Y-%m-%d")
                if start_dt > end_dt:
                    return AgentResponse(
                        success=True,
                        data=f"Khoảng thời gian tìm kiếm không hợp lệ: ngày bắt đầu ({from_date}) không được lớn hơn ngày kết thúc ({to_date}). Vui lòng nhập lại khoảng thời gian chính xác.",
                        metadata={"intent": intent, "extracted_params": {**analysis, "from_date": from_date, "to_date": to_date}}
                    )
            except ValueError:
                # Để cho MCP Server bắt lỗi định dạng ngày
                pass
                
            tool_name = "get_attendance_history"
            arguments = {
                "employee_id": employee_id,
                "from_date": from_date,
                "to_date": to_date
            }
            
        elif intent == "employee_attendance":
            employee_id = analysis.get("employee_id")
            
            # Validation
            if not employee_id or str(employee_id).strip().lower() in ("null", "none", ""):
                return AgentResponse(
                    success=True,
                    data="Vui lòng cung cấp mã nhân viên (ví dụ: E002) để tôi kiểm tra thông tin chuyên cần.",
                    metadata={"intent": intent, "extracted_params": analysis}
                )
            employee_id = str(employee_id).strip().upper()
                
            tool_name = "get_employee_attendance"
            arguments = {
                "employee_id": employee_id
            }
            
        elif intent == "monthly_attendance_statistics":
            month_val = analysis.get("month")
            year_val = analysis.get("year")
            
            # Ưu tiên bắt tháng/năm trực tiếp từ văn bản người dùng nếu có
            slash_match = re.search(r'(?:tháng\s*)?(\d{1,2})[/-](\d{4})', request.message, re.IGNORECASE)
            month_match = re.search(r'tháng\s+(\d+)', request.message, re.IGNORECASE)
            year_match = re.search(r'năm\s+(\d{4})', request.message, re.IGNORECASE)

            def safe_int(value: Any, default: int) -> int:
                if value is None:
                    return default
                val_str = str(value).strip().lower()
                if val_str in ("null", "none", ""):
                    return default
                try:
                    return int(float(val_str))
                except (ValueError, TypeError):
                    return default

            if slash_match:
                month = int(slash_match.group(1))
                year = int(slash_match.group(2))
            else:
                if month_match:
                    month = int(month_match.group(1))
                else:
                    month = safe_int(month_val, 8)

                if year_match:
                    year = int(year_match.group(1))
                else:
                    year = safe_int(year_val, 2026)

            # Validation ATT-11: Kiểm tra khoảng giá trị hợp lệ của tháng và năm
            if month < 1 or month > 12:
                return AgentResponse(
                    success=True,
                    data=f"Tháng {month} không hợp lệ. Vui lòng cung cấp tháng trong khoảng từ 1 đến 12 để tra cứu thống kê.",
                    metadata={"intent": intent, "extracted_params": {"month": month, "year": year}}
                )

            if year < 2000 or year > 2030:
                return AgentResponse(
                    success=True,
                    data=f"Năm {year} không hợp lệ. Vui lòng cung cấp năm trong khoảng từ 2000 đến 2030 để tra cứu thống kê.",
                    metadata={"intent": intent, "extracted_params": {"month": month, "year": year}}
                )
                
            tool_name = "get_monthly_attendance_statistics"
            arguments = {
                "month": month,
                "year": year
            }

        elif intent == "employee_list":
            tool_name = "get_employee_list"
            arguments = {}

        elif intent == "daily_attendance":
            tool_name = "get_daily_attendance"
            d_val = analysis.get("date")
            arguments = {
                "date": d_val if d_val else self._get_today_date()
            }
            
        if not tool_name:
            return AgentResponse(
                success=True,
                data=(
                    "Tôi là trợ lý AI TAS chuyên trách Chuyên cần & Chấm công của công ty.\n\n"
                    "Hiện tại tôi hỗ trợ các chức năng chính:\n"
                    "1. Tra cứu danh sách nhân viên công ty (ví dụ: 'Xem danh sách nhân viên')\n"
                    "2. Tra cứu chấm công theo ngày / hôm nay (ví dụ: 'Xem nhân viên đi làm hôm nay')\n"
                    "3. Xem thông tin chuyên cần nhân viên (ví dụ: 'Xem chuyên cần của nhân viên 009')\n"
                    "4. Xem lịch sử chuyên cần theo khoảng ngày (ví dụ: 'Lịch sử chuyên cần của 009 từ 01/08/2026 đến 22/08/2026')\n"
                    "5. Xem báo cáo thống kê chuyên cần hàng tháng (ví dụ: 'Thống kê chuyên cần tháng 8 năm 2026')\n\n"
                    "Vui lòng đặt câu hỏi rõ hơn để tôi có thể hỗ trợ bạn tốt nhất!"
                ),
                metadata={"intent": intent, "extracted_params": analysis}
            )

        # Bước 3: Gọi MCP Tool qua MCP Client
        try:
            raw_tool_result = self.mcp_client.call_tool(tool_name, arguments)
        except Exception as e:
            return AgentResponse(
                success=False,
                error=f"Lỗi khi truy vấn thông tin qua MCP Server: {e}",
                metadata={"intent": intent, "extracted_params": analysis, "error_code": "MCP_COMMUNICATION_ERROR"}
            )
            
        # Bước 4: Tổng hợp câu trả lời tự nhiên từ kết quả tool
        natural_answer = self._synthesize_response(
            question=request.message,
            intent=intent,
            tool_data=raw_tool_result,
            chat_history_str=history_str
        )
        
        # Đóng gói và trả về AgentResponse
        return AgentResponse(
            success=True,
            data=natural_answer,
            metadata={
                "intent": intent,
                "extracted_params": arguments,
                "raw_data": raw_tool_result
            }
        )
