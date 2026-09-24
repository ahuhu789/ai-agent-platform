# apps/chatbot — Chat API (Root Agent điều phối)

## Chạy

```bash
# Từ thư mục GỐC dự án (ai-agent-platform/), không phải từ trong apps/chatbot/
pip install fastapi uvicorn pydantic-settings
uvicorn apps.chatbot.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs
(Port 8000, KHÔNG dùng 8001 vì trùng Hiring MCP Server SSE.)

## ⚠️ Việc cần làm TRƯỚC khi chạy được

**Merge branch `feature/tra-my-root-agent` vào `main`** (hoặc cherry-pick tối thiểu
2 file `agents/root/root_agent.py` + `agents/root/agent_registry.py`). Code
`apps/chatbot/agent_setup.py` import trực tiếp 2 file này — chưa merge sẽ
`ImportError` ngay lúc khởi động.

## Đã làm gì

- `/chat` — nhận tin nhắn, tạo `AgentRequest`, gọi `RootAgent.handle()` (chạy
  trong threadpool vì đây là hàm đồng bộ, có thể gọi LLM), lưu lịch sử, trả
  `ChatResponse` (kèm cả `success`/`metadata` gốc từ Agent để debug dễ hơn).
- `/conversations` — CRUD danh sách hội thoại.
- `memory_store.py` — cài đặt **tạm thời** của `BaseMemoryStore` (in-memory,
  không persist khi restart). Có ghi chú rõ trong file: khi `shared/memory/`
  (task MEM-01) xong, đổi 1 dòng import là chuyển sang bản chính thức.
- Chỉ đăng ký `HiringAgent` thật vào registry. Attendance/Employee chưa có
  Agent thật trên `main` → cố tình KHÔNG đăng ký Mock, để `RootAgent` tự trả
  "Phân hệ '...' hiện chưa sẵn sàng" — tránh người dùng tưởng nhầm là dữ liệu
  thật. Khi 2 Agent kia xong, chỉ cần thêm 2 dòng `register()` trong
  `agent_setup.py` (đã ghi chú sẵn vị trí).

## Đã test thật (không phải giả định)

Chạy `TestClient` gọi thẳng `RootAgent` + `HiringAgent` thật (không mock) từ
code hiện có của dự án — pass toàn bộ: tạo conversation, hỏi Hiring (ra đúng
data ứng viên), hỏi Attendance (graceful-fail đúng thiết kế), list/get/delete
conversation, xác nhận 404 sau khi xóa.

## Cần bổ sung vào requirements.txt gốc

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic-settings>=2.3.0
```
