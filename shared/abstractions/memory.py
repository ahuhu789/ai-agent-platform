from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class BaseMemoryStore(ABC):
    """
    Interface trừu tượng quản lý bộ nhớ hội thoại (MemoryStore).
    Phụ trách bởi: Vũ Công Nguyên Khang (MEM-01).
    Tham chiếu: docs/AI_Plan.pdf (Mục 3.1 - Thành viên 2)
    """

    @abstractmethod
    def save_message(self, conversation_id: str, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Lưu một message vào lịch sử cuộc trò chuyện."""
        raise NotImplementedError

    @abstractmethod
    def get_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Lấy danh sách messages theo conversation_id (có hỗ trợ giới hạn số lượng)."""
        raise NotImplementedError

    @abstractmethod
    def set_user_context(self, user_id: str, key: str, value: Any) -> None:
        """Lưu ngữ cảnh dùng chung theo người dùng (user-level context)."""
        raise NotImplementedError

    @abstractmethod
    def get_user_context(self, user_id: str, key: str) -> Optional[Any]:
        """Truy xuất ngữ cảnh người dùng theo key."""
        raise NotImplementedError

    @abstractmethod
    def set_agent_context(self, conversation_id: str, agent_name: str, key: str, value: Any) -> None:
        """Lưu ngữ cảnh riêng biệt cho từng agent trong phiên hội thoại."""
        raise NotImplementedError

    @abstractmethod
    def get_agent_context(self, conversation_id: str, agent_name: str, key: str) -> Optional[Any]:
        """Lấy ngữ cảnh riêng của agent."""
        raise NotImplementedError
