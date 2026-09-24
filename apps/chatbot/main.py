"""
Entry point Chat API. Chạy độc lập:
    uvicorn apps.chatbot.main:app --reload --port 8000
(chạy từ thư mục gốc dự án, để import agents.*/shared.* hoạt động đúng)

Swagger UI: http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from apps.chatbot.config import settings
from apps.chatbot.routers import chat, conversations

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "API cho /chat (route qua Root Agent -> Domain Agent) và /conversations "
        "(quản lý lịch sử hội thoại). Swagger UI tự sinh tại /docs."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversations.router)
app.include_router(chat.router)


@app.get("/health", tags=["Health"], summary="Kiểm tra service còn sống")
def health():
    return {"status": "ok"}
