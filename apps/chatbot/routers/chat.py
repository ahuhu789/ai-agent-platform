from fastapi import APIRouter, HTTPException

from apps.chatbot import schemas
from apps.chatbot.services.chat_service import chat_service

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "",
    response_model=schemas.ChatResponse,
    summary="Gửi tin nhắn tới hệ thống Multi-Agent (Root Agent điều phối)",
    description=(
        "Nếu không truyền conversation_id, hệ thống tự tạo conversation mới. "
        "Root Agent sẽ phân loại câu hỏi thuộc phân hệ nào (Tuyển dụng / Chuyên cần / "
        "Nhân sự) và chuyển tới đúng Domain Agent xử lý thông qua Service layer."
    ),
)
async def chat(payload: schemas.ChatRequest):
    try:
        result = await chat_service.process_chat(
            message=payload.message,
            conversation_id=payload.conversation_id,
            user_id=payload.user_id or "default_user",
        )
        return schemas.ChatResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lỗi máy chủ nội bộ: {str(exc)}")
