"""Web UI runner for AI Agent Platform."""
import uvicorn

if __name__ == "__main__":
    print("🚀 Đang khởi động AI Agent Platform Web UI tại: http://localhost:8000")
    uvicorn.run("apps.chatbot.main:app", host="127.0.0.1", port=8000, reload=True)
