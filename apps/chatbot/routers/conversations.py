from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from apps.chatbot import schemas
from apps.chatbot.memory_store import memory_store

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("", response_model=schemas.ConversationOut, summary="Tạo conversation mới")
def create_conversation(data: schemas.ConversationCreate):
    uid = data.user_id or "default_user"
    conversation_id = memory_store.create_conversation(title=data.title, user_id=uid)
    meta = memory_store.get_conversation_meta(conversation_id, user_id=uid)
    if not meta:
        raise HTTPException(status_code=500, detail="Không thể tạo conversation")
    return meta


@router.get("", response_model=List[schemas.ConversationOut], summary="Liệt kê tất cả conversation của người dùng")
def list_conversations(user_id: str = Query(default="default_user", description="ID người dùng sở hữu conversation")):
    return memory_store.list_conversations(user_id=user_id)


@router.get(
    "/{conversation_id}",
    response_model=schemas.ConversationDetailOut,
    summary="Lấy chi tiết 1 conversation kèm toàn bộ tin nhắn",
)
def get_conversation(
    conversation_id: str,
    user_id: str = Query(default="default_user", description="ID người dùng"),
):
    meta = memory_store.get_conversation_meta(conversation_id, user_id=user_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Không tìm thấy conversation hoặc không thuộc quyền sở hữu")
    return {**meta, "messages": memory_store.get_messages(conversation_id, user_id=user_id)}


@router.get(
    "/{conversation_id}/messages",
    response_model=List[schemas.MessageOut],
    summary="Lấy danh sách tin nhắn của 1 conversation (AI_Plan Mục 3.1 - Thành viên 4)",
)
def get_conversation_messages(
    conversation_id: str,
    limit: Optional[int] = Query(default=None, description="Số lượng tin nhắn tối đa"),
    user_id: str = Query(default="default_user", description="ID người dùng"),
):
    meta = memory_store.get_conversation_meta(conversation_id, user_id=user_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Không tìm thấy conversation hoặc không thuộc quyền sở hữu")
    return memory_store.get_messages(conversation_id, limit=limit, user_id=user_id)


@router.delete("/{conversation_id}", summary="Xóa 1 conversation (và toàn bộ tin nhắn liên quan)")
def delete_conversation(
    conversation_id: str,
    user_id: str = Query(default="default_user", description="ID người dùng"),
):
    ok = memory_store.delete_conversation(conversation_id, user_id=user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy conversation hoặc không thuộc quyền sở hữu")
    return {"success": True}
