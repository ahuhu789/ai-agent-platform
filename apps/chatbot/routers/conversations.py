from fastapi import APIRouter, HTTPException
from typing import List

from apps.chatbot import schemas
from apps.chatbot.memory_store import memory_store

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=schemas.ConversationOut, summary="Tạo conversation mới")
def create_conversation(data: schemas.ConversationCreate):
    conversation_id = memory_store.create_conversation(title=data.title)
    return memory_store.get_conversation_meta(conversation_id)


@router.get("", response_model=List[schemas.ConversationOut], summary="Liệt kê tất cả conversation")
def list_conversations():
    return memory_store.list_conversations()


@router.get(
    "/{conversation_id}",
    response_model=schemas.ConversationDetailOut,
    summary="Lấy chi tiết 1 conversation kèm toàn bộ tin nhắn",
)
def get_conversation(conversation_id: str):
    meta = memory_store.get_conversation_meta(conversation_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Không tìm thấy conversation")
    return {**meta, "messages": memory_store.get_messages(conversation_id)}


@router.delete("/{conversation_id}", summary="Xóa 1 conversation (và toàn bộ tin nhắn liên quan)")
def delete_conversation(conversation_id: str):
    ok = memory_store.delete_conversation(conversation_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy conversation")
    return {"success": True}
