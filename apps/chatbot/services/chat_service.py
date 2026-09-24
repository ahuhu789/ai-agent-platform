"""
Service Layer xử lý nghiệp vụ cho Chat API.
Tách biệt Controller (Router) khỏi Business Logic theo kiến trúc AI_Plan (Mục 4.3).
Luồng: API Router -> ChatService -> RootAgent -> Domain Agent -> MCP Client -> MCP Server.
"""
from typing import Any, Dict, Optional
from fastapi.concurrency import run_in_threadpool

from shared.abstractions.agent import AgentRequest, AgentResponse
from shared.logger import setup_logger
from apps.chatbot.agent_setup import root_agent as default_root_agent
from apps.chatbot.memory_store import memory_store as default_memory_store

logger = setup_logger("fme.chat_service")


class ChatService:
    """Service điều phối nghiệp vụ chat, quản lý session hội thoại và gọi Root Agent."""

    def __init__(self, root_agent=None, memory_store=None):
        self.root_agent = root_agent or default_root_agent
        self.memory_store = memory_store or default_memory_store

    async def process_chat(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        user_id: str = "default_user",
    ) -> Dict[str, Any]:
        """Xử lý một lượt tin nhắn người dùng.

        Args:
            message: Nội dung tin nhắn người dùng.
            conversation_id: ID cuộc hội thoại (nếu có).
            user_id: ID người dùng.

        Returns:
            Dict[str, Any]: Kết quả phản hồi chứa conversation_id, reply, success, metadata, messages.

        Raises:
            ValueError: Khi conversation_id được truyền nhưng không tồn tại hoặc không thuộc user.
        """
        user_id = user_id or "default_user"

        # 1. Xác định hoặc tạo mới cuộc hội thoại
        if conversation_id:
            meta = self.memory_store.get_conversation_meta(conversation_id, user_id=user_id)
            if meta is None:
                raise ValueError("Không tìm thấy conversation")
            active_conv_id = conversation_id
        else:
            active_conv_id = self.memory_store.create_conversation(user_id=user_id)

        # 2. Lưu tin nhắn của người dùng vào Memory
        self.memory_store.save_message(
            active_conv_id,
            role="user",
            content=message,
            user_id=user_id,
        )

        # 3. Lấy ngữ cảnh đa lượt từ Memory Store
        chat_context = self.memory_store.build_chat_context(active_conv_id, user_id=user_id)

        # 4. Tạo AgentRequest và thực thi qua Root Agent (chạy trong threadpool an toàn)
        agent_request = AgentRequest(
            message=message,
            conversation_id=active_conv_id,
            user_id=user_id,
            context=chat_context,
        )

        try:
            agent_response: AgentResponse = await run_in_threadpool(self.root_agent.handle, agent_request)
        except Exception as exc:
            logger.error("Lỗi ngoại lệ khi Root Agent xử lý: %s", exc, exc_info=True)
            agent_response = AgentResponse(
                success=False,
                error=f"Đã có lỗi xảy ra trong quá trình xử lý: {str(exc)}",
                metadata={"source": "chat_service", "error": str(exc)},
            )

        # 5. Định dạng văn bản trả lời cho người dùng
        if agent_response.success and agent_response.data:
            reply_text = agent_response.data.get("response") or str(agent_response.data)
        else:
            reply_text = agent_response.error or "Xin lỗi, tôi không thể xử lý yêu cầu lúc này."

        # 6. Lưu phản hồi của Assistant và cập nhật entity/ngữ cảnh vào Memory
        self.memory_store.save_message(
            active_conv_id,
            role="assistant",
            content=reply_text,
            metadata=agent_response.metadata,
            user_id=user_id,
        )
        self.memory_store.track_interaction(
            conversation_id=active_conv_id,
            user_id=user_id,
            user_message=message,
            agent_response_data=agent_response.data if isinstance(agent_response.data, dict) else {},
            metadata=agent_response.metadata,
        )

        # 7. Trả về kết quả
        return {
            "conversation_id": active_conv_id,
            "reply": reply_text,
            "success": agent_response.success,
            "metadata": agent_response.metadata,
            "messages": self.memory_store.get_messages(active_conv_id, user_id=user_id),
        }


# Singleton dùng chung
chat_service = ChatService()
