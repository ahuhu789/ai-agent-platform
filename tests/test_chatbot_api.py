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
