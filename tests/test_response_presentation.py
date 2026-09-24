"""
Kiểm thử bộ định dạng hiển thị kết quả (Presentation & Rendering Test Suite).
Bảo đảm đáp ứng đầy đủ 6 kịch bản theo yêu cầu nghiệp vụ:
  a. Danh sách nhiều bản ghi: định dạng bảng Markdown chuẩn (| STT | ... |), căn phải số liệu (|---:|), có dòng tổng kết.
  b. Chi tiết 1 bản ghi: định dạng thẻ chi tiết (bullet points), không ép thành bảng 1 dòng, giữ nguyên mã định danh.
  c. Danh sách rỗng: thông báo lịch sự, không bị vỡ bảng hay in bảng trống.
  d. Khi MCP Tool trả về lỗi: hiển thị thông báo lỗi rõ ràng, không crash.
  e. Câu hỏi phi cấu trúc / không liên quan bảng: văn bản chào hỏi, hướng dẫn tự nhiên.
  f. Ký tự đặc biệt: email (@), số điện thoại, tiếng Việt có dấu không bị escape lỗi (\\@, \\*, \\|).
"""
import re
import pytest

from shared.abstractions.agent import AgentRequest
from agents.hiring.hiring_agent import HiringAgent
from agents.employee.employee_agent import EmployeeAgent
from agents.attendance.attendance_agent import AttendanceAgent


@pytest.fixture
def hiring_agent():
    return HiringAgent(openai_client=False)


@pytest.fixture
def employee_agent():
    return EmployeeAgent(openai_client=False)


@pytest.fixture
def attendance_agent():
    return AttendanceAgent(openai_client=False)


# --------------------------------------------------------------------------
# Kịch bản a: Danh sách ứng viên / nhân sự có nhiều bản ghi
# --------------------------------------------------------------------------
def test_scenario_a_multi_record_candidate_table(hiring_agent):
    """Kịch bản a: Danh sách nhiều ứng viên phải hiển thị dưới dạng bảng Markdown chuẩn, có căn lề số liệu và dòng tổng số."""
    req = AgentRequest(message="Có bao nhiêu ứng viên đang chờ phỏng vấn?")
    res = hiring_agent.handle(req)
    assert res.success is True
    reply = res.data["response"]

    # 1. Chứa tiêu đề Markdown
    assert "###" in reply
    # 2. Chứa cấu trúc bảng Markdown với các cột chính
    assert "| STT |" in reply or "| STT" in reply
    assert "| Mã CV |" in reply or "Mã" in reply
    assert "| Họ và tên |" in reply
    assert "| Vị trí |" in reply
    # 3. Cột số liệu căn phải (|---:|)
    assert "|---:|" in reply
    # 4. Tuyệt đối không chứa ký tự escape gạch đứng \|
    assert "\\|" not in reply
    # 5. Có dòng tổng số kết thúc
    assert "**Tổng số:**" in reply or "Tổng số:" in reply
    # 6. Kiểm tra các dòng dữ liệu (nhiều hơn 1 ứng viên)
    table_rows = [line for line in reply.split("\n") if line.strip().startswith("|") and not re.match(r"^\|\s*:?-+:?", line.strip())]
    assert len(table_rows) >= 3  # Header + ít nhất 2 dòng data


def test_scenario_a_multi_record_employee_table(employee_agent):
    """Kịch bản a (mở rộng): Danh sách các phòng ban hiển thị dạng bảng chuẩn."""
    req = AgentRequest(message="Công ty có những phòng ban nào?")
    res = employee_agent.handle(req)
    assert res.success is True
    reply = res.data["response"]

    assert "| STT |" in reply
    assert "| Mã PB |" in reply
    assert "| Tên phòng ban |" in reply
    assert "|---:|" in reply
    assert "\\|" not in reply
    assert "Tổng số:" in reply or "**Tổng số:**" in reply


# --------------------------------------------------------------------------
# Kịch bản b: Chi tiết 1 bản ghi
# --------------------------------------------------------------------------
def test_scenario_b_single_candidate_detail(hiring_agent):
    """Kịch bản b: Xem chi tiết 1 ứng viên phải hiển thị dạng chi tiết / bullet points, không ép thành bảng 1 dòng."""
    req = AgentRequest(message="Cho tôi xem hồ sơ chi tiết của ứng viên UV001")
    res = hiring_agent.handle(req)
    assert res.success is True
    reply = res.data["response"]

    # Phải có mã định danh
    assert "UV001" in reply
    # Định dạng bullet point chi tiết
    assert "- **Mã ứng viên:**" in reply or "UV001" in reply
    assert "- **Họ và tên:**" in reply or "Nguyễn Văn Tuấn" in reply
    assert "- **Vị trí" in reply
    assert "- **Trạng thái" in reply
    assert "- **Kinh nghiệm" in reply
    # Không ép thành bảng (| STT |...)
    assert "| STT |" not in reply


def test_scenario_b_single_employee_profile(employee_agent):
    """Kịch bản b (mở rộng): Xem chi tiết 1 nhân viên dạng card."""
    req = AgentRequest(message="Tìm thông tin nhân viên có mã NV001")
    res = employee_agent.handle(req)
    assert res.success is True
    reply = res.data["response"]

    assert "NV001" in reply
    assert "Nguyễn Văn A" in reply
    assert "- **Mã nhân viên:**" in reply
    assert "- **Phòng ban:**" in reply
    assert "| STT |" not in reply


# --------------------------------------------------------------------------
# Kịch bản c: Danh sách rỗng (Không tìm thấy bản ghi)
# --------------------------------------------------------------------------
def test_scenario_c_empty_candidate_search(hiring_agent):
    """Kịch bản c: Tìm kiếm không có ứng viên nào -> phản hồi lịch sự, không vẽ bảng rỗng."""
    req = AgentRequest(message="Tìm ứng viên có kỹ năng GolangAndRustExpert9999")
    res = hiring_agent.handle(req)
    assert res.success is True
    reply = res.data["response"]

    # Thông báo lịch sự
    assert "không tìm thấy" in reply.lower() or "hiện tại không" in reply.lower()
    # Tuyệt đối không xuất hiện khung bảng trống
    assert "| STT |" not in reply
    assert "|---:|" not in reply


def test_scenario_c_empty_employee_search(employee_agent):
    """Kịch bản c (mở rộng): Tìm nhân viên không tồn tại."""
    req = AgentRequest(message="Tìm nhân viên có tên TenKhongHeTonTaiTrongHeThong")
    res = employee_agent.handle(req)
    assert res.success is True
    reply = res.data["response"]

    assert "không tìm thấy" in reply.lower()
    assert "| STT |" not in reply


# --------------------------------------------------------------------------
# Kịch bản d: Khi MCP Tool trả về lỗi
# --------------------------------------------------------------------------
def test_scenario_d_tool_error_handling(hiring_agent):
    """Kịch bản d: Tool trả về lỗi (mã không tồn tại / sai format) -> trả thông báo lỗi rõ ràng, không crash."""
    req = AgentRequest(message="Cho tôi thông tin ứng viên có mã UV999")
    res = hiring_agent.handle(req)
    # res.success phản ánh trạng thái gọi tool (False khi không tìm thấy mã)
    assert res.success is False
    reply = res.data["response"]
    assert "Không thể thực hiện" in reply or "Không tìm thấy" in reply or "❌" in reply


# --------------------------------------------------------------------------
# Kịch bản e: Câu hỏi không liên quan bảng (Chào hỏi, hướng dẫn)
# --------------------------------------------------------------------------
def test_scenario_e_general_greeting_query(hiring_agent, employee_agent, attendance_agent):
    """Kịch bản e: Câu hỏi tổng quan -> render văn bản thường, không vẽ bảng vô cớ."""
    for agent in [hiring_agent, employee_agent, attendance_agent]:
        res = agent._handle_general_query("Xin chào bạn có thể giúp gì?")
        assert res.success is True
        reply = res.data["response"]
        assert "Chào" in reply or "chào" in reply
        assert "| STT |" not in reply
        assert "|---:|" not in reply


# --------------------------------------------------------------------------
# Kịch bản f: Dữ liệu chứa ký tự đặc biệt (@, SĐT, dấu tiếng Việt)
# --------------------------------------------------------------------------
def test_scenario_f_special_characters_email_phone_accents(hiring_agent):
    """Kịch bản f: Dữ liệu có email, số điện thoại, tiếng Việt có dấu hiển thị chuẩn, không bị escape lỗi."""
    req = AgentRequest(message="Cho tôi xem hồ sơ chi tiết của ứng viên UV001")
    res = hiring_agent.handle(req)
    reply = res.data["response"]

    # 1. Email chứa @ bình thường, tuyệt đối không bị escape thành \@
    assert "@" in reply
    assert "\\@" not in reply

    # 2. Ký tự Markdown không bị escape lỗi
    assert "\\*" not in reply
    assert "\\|" not in reply

    # 3. Tiếng Việt có dấu nguyên vẹn
    assert any(ch in reply for ch in ["ễ", "ắ", "ấ", "ư", "ơ", "đ", "Đ"])
