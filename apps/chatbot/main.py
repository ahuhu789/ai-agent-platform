"""
Entry point Chat API. Chạy độc lập:
    uvicorn apps.chatbot.main:app --reload --port 8000
(chạy từ thư mục gốc dự án, để import agents.*/shared.* hoạt động đúng)

Swagger UI: http://localhost:8000/docs
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv(override=True)
logging.getLogger("httpx").setLevel(logging.INFO)

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from apps.chatbot.config import settings
from apps.chatbot.agent_setup import mcp_client
from apps.chatbot.routers import chat, conversations, settings as settings_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await asyncio.to_thread(mcp_client.connect_all)
    try:
        yield
    finally:
        await asyncio.to_thread(mcp_client.disconnect_all)

app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=(
        "API cho /chat (route qua Root Agent -> Domain Agent), /conversations "
        "(quản lý lịch sử hội thoại) và /settings (quản lý file .env và cấu hình LLM). Swagger UI tự sinh tại /docs."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(conversations.router)
app.include_router(chat.router)
app.include_router(settings_router.router)

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


@app.get("/health/ready", tags=["Health"], summary="Kiểm tra các MCP Server đã sẵn sàng")
def readiness(response: Response):
    servers = dict(mcp_client.server_status)
    ready = bool(servers) and all(state == "connected" for state in servers.values())
    response.status_code = 200 if ready else 503
    return {"status": "ready" if ready else "not_ready", "servers": servers}
