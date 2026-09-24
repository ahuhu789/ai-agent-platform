from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from shared.abstractions.agent import AgentRequest

from apps.chatbot import schemas
from apps.chatbot.agent_setup import root_agent
from apps.chatbot.memory_store import memory_store

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post(
    "",
    response_model=schemas.ChatResponse,
    summary="Gửi tin nhắn tới hệ thống Multi-Agent (Root Agent điều phối)",
    description=(
        "Nếu không truyền conversation_id, hệ thống tự tạo conversation mới. "
        "Root Agent sẽ phân loại câu hỏi thuộc phân hệ nào (Tuyển dụng / Chuyên cần / "
        "Nhân sự) và chuyển tới đúng Domain Agent xử lý."
    ),
)
async def chat(payload: schemas.ChatRequest):
    user_id = payload.user_id or "default_user"

    # 1. Xác định (hoặc tạo mới) conversation
    if payload.conversation_id:
        if memory_store.get_conversation_meta(payload.conversation_id, user_id=user_id) is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy conversation")
        conversation_id = payload.conversation_id
    else:
        conversation_id = memory_store.create_conversation(user_id=user_id)

    # 2. Lưu tin nhắn của user
    memory_store.save_message(conversation_id, role="user", content=payload.message, user_id=user_id)

    # 3. Lấy ngữ cảnh hội thoại đa lượt từ Memory Store
    chat_context = memory_store.build_chat_context(conversation_id, user_id=user_id)

    # 4. Gọi Root Agent (đồng bộ, có thể gọi LLM -> chạy trong threadpool)
    agent_request = AgentRequest(
        message=payload.message,
        conversation_id=conversation_id,
        user_id=user_id,
        context=chat_context,
    )
    agent_response = await run_in_threadpool(root_agent.handle, agent_request)

    # 5. Trích câu trả lời hiển thị cho người dùng
    if agent_response.success and agent_response.data:
        reply_text = agent_response.data.get("response") or str(agent_response.data)
    else:
        reply_text = agent_response.error or "Xin lỗi, đã có lỗi xảy ra."

    # 6. Lưu câu trả lời của assistant và cập nhật entity/ngữ cảnh vào Memory
    memory_store.save_message(
        conversation_id,
        role="assistant",
        content=reply_text,
        metadata=agent_response.metadata,
        user_id=user_id,
    )
    memory_store.track_interaction(
        conversation_id=conversation_id,
        user_id=user_id,
        user_message=payload.message,
        agent_response_data=agent_response.data if isinstance(agent_response.data, dict) else {},
        metadata=agent_response.metadata,
    )

    return schemas.ChatResponse(
        conversation_id=conversation_id,
        reply=reply_text,
        success=agent_response.success,
        metadata=agent_response.metadata,
        messages=memory_store.get_messages(conversation_id, user_id=user_id),
    )

