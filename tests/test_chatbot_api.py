import pytest
from fastapi.testclient import TestClient

from apps.chatbot.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "AI Agent Platform" in response.text



def test_chat_hiring_flow(client):
    response = client.post("/chat", json={"message": "Có bao nhiêu ứng viên đang chờ phỏng vấn?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "conversation_id" in data
    assert data["metadata"]["intent"] == "hiring"
    assert data["metadata"]["tool_used"] == "search_candidates"
    assert len(data["messages"]) == 2  # 1 user + 1 assistant


def test_chat_attendance_flow(client):
    response = client.post("/chat", json={"message": "Tháng này nhân viên A đi làm bao nhiêu ngày?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["metadata"]["intent"] == "attendance"
    assert data["metadata"]["tool_used"] == "get_monthly_attendance"
    assert "18" in data["reply"]


def test_chat_employee_flow(client):
    response = client.post("/chat", json={"message": "Nhân viên A thuộc phòng ban nào?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["metadata"]["intent"] == "employee"
    assert data["metadata"]["tool_used"] == "get_employee_department"
    assert "Phòng Kỹ thuật" in data["reply"]



def test_chat_multi_turn_memory_retention(client):
    # Lượt 1: Hỏi về Nhân viên A thuộc phòng ban nào (Employee domain)
    res1 = client.post("/chat", json={"message": "Nhân viên A thuộc phòng ban nào?"})
    assert res1.status_code == 200
    conv_id = res1.json()["conversation_id"]
    assert "Phòng Kỹ thuật" in res1.json()["reply"]

    # Lượt 2: Hỏi tiếp về chuyên cần trong cùng conversation nhưng KHÔNG nhắc lại tên/mã nhân viên!
    # Hệ thống phải nhớ context từ Lượt 1 để trả lời chính xác số ngày đi làm của Nhân viên A (NV001)!
    res2 = client.post("/chat", json={"conversation_id": conv_id, "message": "Tháng này đi làm bao nhiêu ngày?"})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["success"] is True
    assert data2["metadata"]["intent"] == "attendance"
    assert "18" in data2["reply"]
    assert "Nguyễn Văn A" in data2["reply"]


def test_chat_fallback_out_of_scope(client):
    response = client.post("/chat", json={"message": "Thời tiết hôm nay thế nào?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "chưa hiểu câu hỏi này thuộc phân hệ nào" in data["reply"]


def test_conversations_crud(client):
    # 1. Create conversation
    create_res = client.post("/conversations", json={"title": "Test Hội thoại"})
    assert create_res.status_code == 200
    conv_id = create_res.json()["id"]

    # 2. Get conversation
    get_res = client.get(f"/conversations/{conv_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == conv_id

    # 3. List conversations
    list_res = client.get("/conversations")
    assert list_res.status_code == 200
    assert any(c["id"] == conv_id for c in list_res.json())

    # 4. Delete conversation
    del_res = client.delete(f"/conversations/{conv_id}")
    assert del_res.status_code == 200
    assert del_res.json() == {"success": True}

    # 5. Verify deleted
    not_found = client.get(f"/conversations/{conv_id}")
    assert not_found.status_code == 404


def test_conversations_messages_and_user_isolation(client):
    # Tạo conversation cho user_alice
    res_a = client.post("/conversations", json={"title": "Alice Chat", "user_id": "user_alice"})
    assert res_a.status_code == 200
    conv_alice = res_a.json()["id"]

    # Gửi tin nhắn
    chat_res = client.post("/chat", json={
        "conversation_id": conv_alice,
        "message": "Có bao nhiêu ứng viên đang chờ phỏng vấn?",
        "user_id": "user_alice"
    })
    assert chat_res.status_code == 200

    # Lấy messages qua endpoint mới GET /conversations/{id}/messages
    msg_res = client.get(f"/conversations/{conv_alice}/messages?user_id=user_alice")
    assert msg_res.status_code == 200
    messages = msg_res.json()
    assert len(messages) >= 2

    # Kiểm tra User Isolation (user_bob không thể truy cập conversation của user_alice)
    bob_res = client.get(f"/conversations/{conv_alice}?user_id=user_bob")
    assert bob_res.status_code == 404

    bob_msg_res = client.get(f"/conversations/{conv_alice}/messages?user_id=user_bob")
    assert bob_msg_res.status_code == 404


def test_ocr_health_api(client):
    response = client.get("/ocr/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "engine" in data
    assert data["engine"] == "tesseract"


def test_ocr_process_api(client):
    import io
    from PIL import Image, ImageDraw

    # Tạo ảnh mẫu đơn giản
    img = Image.new("RGB", (300, 80), color="white")
    draw = ImageDraw.Draw(img)
    draw.text((20, 25), "FASTAPI OCR", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    response = client.post(
        "/ocr/process",
        files={"file": ("test_doc.png", buf.getvalue(), "image/png")},
        data={"lang": "eng", "preprocess": "true"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "FASTAPI" in data["text"] or "OCR" in data["text"]
    assert data["metadata"]["source"] == "test_doc.png"
    assert data["metadata"]["engine"] == "tesseract"


def test_ocr_process_pdf_api(client):
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "HOP DONG LAO DONG PDF TEST")
    pdf_bytes = doc.tobytes()

    response = client.post(
        "/ocr/process",
        files={"file": ("contract.pdf", pdf_bytes, "application/pdf")},
        data={"lang": "vie+eng", "preprocess": "true"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "HOP DONG LAO DONG" in data["text"]
    assert data["metadata"]["source"] == "contract.pdf"
    assert data["metadata"]["image_format"] == "PDF"

