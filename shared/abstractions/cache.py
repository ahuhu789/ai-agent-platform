from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseCache(ABC):
    """
    Interface trừu tượng cho hệ thống bộ nhớ đệm (Cache).
    Phụ trách bởi: Thành viên 5 - Nhóm Core Chatbot.
    Tham chiếu: docs/AI_Plan.pdf (Mục 3.1 - Thành viên 5)
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Lấy giá trị từ cache theo key."""
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Lưu giá trị vào cache kèm thời gian hết hạn (TTL)."""
        raise NotImplementedError

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Xóa key khỏi cache."""
        raise NotImplementedError
