"""
Entry point Chat API. Chạy độc lập:
    uvicorn apps.chatbot.main:app --reload --port 8000
(chạy từ thư mục gốc dự án, để import agents.*/shared.* hoạt động đúng)

Swagger UI: http://localhost:8000/docs
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

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

# Mount static web demo UI
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "AI Agent Platform Demo API. Visit /docs for Swagger UI."}


@app.get("/health", tags=["Health"], summary="Kiểm tra service còn sống")
def health():
    return {"status": "ok"}

