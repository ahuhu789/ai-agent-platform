"""
Adapter kết nối Chat API với module Memory chính thức (shared.memory.factory).
Cung cấp các phương thức cần thiết cho /chat và /conversations,
đồng thời ủy quyền lưu trữ cho MemoryStore (InMemoryStore hoặc RedisMemoryStore).
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.abstractions.memory import Message
from shared.memory.factory import create_memory_store


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatbotMemoryAdapter:
    def __init__(self, provider: Optional[str] = None):
        self._store = create_memory_store(provider)
        self._titles: Dict[str, str] = {}  # conversation_id -> title

    def create_conversation(self, title: Optional[str] = None, user_id: str = "default_user") -> str:
        conv = self._store.create_conversation(user_id=user_id)
        conv_id = conv.conversation_id
        self._titles[conv_id] = title or "Cuộc trò chuyện mới"
        return conv_id

    def get_conversation_meta(self, conversation_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conv = self._store.get_conversation(conversation_id, user_id=user_id)
        if not conv:
            return None
        return {
            "id": conv.conversation_id,
            "title": self._titles.get(conv.conversation_id, "Cuộc trò chuyện mới"),
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
        }

    def list_conversations(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        conversations = self._store.list_conversations(user_id=user_id)
        result = []
        for c in conversations:
            result.append({
                "id": c.conversation_id,
                "title": self._titles.get(c.conversation_id, "Cuộc trò chuyện mới"),
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            })
        return result

    def delete_conversation(self, conversation_id: str, user_id: Optional[str] = None) -> bool:
        self._titles.pop(conversation_id, None)
        return self._store.delete_conversation(conversation_id, user_id=user_id)

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> None:
        msg = Message(role=role, content=content, metadata=metadata or {})
        self._store.append_message(conversation_id, msg, user_id=user_id)

    def get_messages(self, conversation_id: str, limit: Optional[int] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        messages = self._store.get_messages(conversation_id, user_id=user_id)
        if limit:
            messages = messages[-limit:]
        return [
            {
                "id": m.metadata.get("id") or str(uuid.uuid4()),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ]

    def set_user_context(self, user_id: str, key: str, value: Any) -> None:
        self._store.update_user_context(user_id, {key: value})

    def get_user_context(self, user_id: str, key: str) -> Optional[Any]:
        return self._store.get_user_context(user_id).get(key)

    def get_all_user_context(self, user_id: str) -> Dict[str, Any]:
        return self._store.get_user_context(user_id)

    def update_user_context(self, user_id: str, data: Dict[str, Any]) -> None:
        self._store.update_user_context(user_id, data)

    def set_agent_context(self, user_id: str, agent_name: str, key: str, value: Any) -> None:
        self._store.update_agent_context(user_id, agent_name, {key: value})

    def get_agent_context(self, user_id: str, agent_name: str, key: str) -> Optional[Any]:
        return self._store.get_agent_context(user_id, agent_name).get(key)

    def build_chat_context(self, conversation_id: str, user_id: str = "default_user") -> Dict[str, Any]:
        """Build rich conversation & user context for Multi-turn agent reasoning."""
        import re
        from shared.memory.context_keys import (
            LAST_AGENT,
            LAST_CANDIDATE_ID,
            LAST_DEPARTMENT,
            LAST_EMPLOYEE_ID,
            LAST_EMPLOYEE_NAME,
        )

        user_ctx = dict(self._store.get_user_context(user_id) or {})
        messages = self.get_messages(conversation_id, limit=10, user_id=user_id)

        last_cand = user_ctx.get(LAST_CANDIDATE_ID) or user_ctx.get("last_candidate_id")
        last_emp = user_ctx.get(LAST_EMPLOYEE_ID) or user_ctx.get("last_employee_id")
        last_dept = user_ctx.get(LAST_DEPARTMENT) or user_ctx.get("last_department")
        last_emp_name = user_ctx.get(LAST_EMPLOYEE_NAME) or user_ctx.get("last_employee_name")
        last_agent = user_ctx.get(LAST_AGENT) or user_ctx.get("last_agent")

        # Scan recent messages to recover context if missing
        for m in reversed(messages):
            content = m.get("content", "")
            if not last_cand:
                cand_match = re.search(r"\b(UV[- ]?\d{3,4})\b", content, re.IGNORECASE)
                if cand_match:
                    last_cand = cand_match.group(1).upper().replace(" ", "").replace("-", "")
            if not last_emp:
                emp_match = re.search(r"\b(NV[- ]?\d{3,4})\b", content, re.IGNORECASE)
                if emp_match:
                    last_emp = emp_match.group(1).upper().replace(" ", "").replace("-", "")
            if not last_emp_name:
                name_match = re.search(r"nhân viên\s+([A-ZÀ-Ỹa-zà-ỹ\s]+?)(?:\s+thuộc|\s+ở|\s+đi|\s+có|$)", content, re.IGNORECASE)
                if name_match:
                    found_name = name_match.group(1).strip()
                    if len(found_name) <= 25 and not any(k in found_name.lower() for k in ["này", "đó", "nào"]):
                        last_emp_name = found_name
            if not last_dept:
                for d in ["Kỹ thuật", "Nhân sự", "Kế toán", "Kinh doanh", "Marketing", "Vận hành"]:
                    if d.lower() in content.lower():
                        last_dept = f"Phòng {d}"
                        break

        ctx = {
            **user_ctx,
            "conversation_id": conversation_id,
            "user_id": user_id,
            "last_candidate_id": last_cand,
            "last_employee_id": last_emp,
            "last_employee_name": last_emp_name,
            "last_department": last_dept,
            "last_agent": last_agent,
            LAST_CANDIDATE_ID: last_cand,
            LAST_EMPLOYEE_ID: last_emp,
            LAST_EMPLOYEE_NAME: last_emp_name,
            LAST_DEPARTMENT: last_dept,
            LAST_AGENT: last_agent,
            "chat_history": messages,
        }
        return ctx

    def track_interaction(
        self,
        conversation_id: str,
        user_id: str,
        user_message: str,
        agent_response_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Extract and persist entities and agent state into user context for subsequent turns."""
        import re
        from shared.memory.context_keys import (
            LAST_AGENT,
            LAST_CANDIDATE_ID,
            LAST_DEPARTMENT,
            LAST_EMPLOYEE_ID,
            LAST_EMPLOYEE_NAME,
        )

        updates: Dict[str, Any] = {}
        meta = metadata or {}
        data = agent_response_data or {}
        params = meta.get("parameters") or data.get("parameters") or {}

        # 1. Track Agent
        agent = meta.get("agent") or meta.get("intent")
        if not agent:
            source = meta.get("source")
            if source and source not in ["root_agent", "root", "chat_service", "system"]:
                agent = source
        if agent and agent not in ["root_agent", "root", "chat_service", "system"]:
            updates[LAST_AGENT] = agent
            updates["last_agent"] = agent

        # 2. Track Candidate ID
        cand_id = params.get("candidate_id")
        if not cand_id:
            m = re.search(r"\b(UV[- ]?\d{3,4})\b", user_message, re.IGNORECASE)
            if m:
                cand_id = m.group(1).upper().replace(" ", "").replace("-", "")
        if not cand_id and isinstance(data.get("raw_tool_result"), dict):
            cand_id = data["raw_tool_result"].get("data", {}).get("id") if isinstance(data["raw_tool_result"].get("data"), dict) else None
        if cand_id:
            updates[LAST_CANDIDATE_ID] = cand_id
            updates["last_candidate_id"] = cand_id

        # 3. Track Employee ID & Name
        emp_id = params.get("employee_id")
        if not emp_id:
            m = re.search(r"\b(NV[- ]?\d{3,4})\b", user_message, re.IGNORECASE)
            if m:
                emp_id = m.group(1).upper().replace(" ", "").replace("-", "")
        if not emp_id and isinstance(data.get("raw_tool_result"), dict):
            raw_data = data["raw_tool_result"].get("data")
            if isinstance(raw_data, dict):
                emp_id = raw_data.get("employee_id") or raw_data.get("id")
        if emp_id and str(emp_id).upper() != "ALL":
            updates[LAST_EMPLOYEE_ID] = emp_id
            updates["last_employee_id"] = emp_id

        # Employee name
        emp_name = None
        if isinstance(data.get("raw_tool_result"), dict):
            raw_data = data["raw_tool_result"].get("data")
            if isinstance(raw_data, dict):
                emp_name = raw_data.get("employee_name") or raw_data.get("name")
        if emp_name and emp_name not in ("Tất cả nhân viên", "Toàn bộ nhân viên", "Nhân viên"):
            updates[LAST_EMPLOYEE_NAME] = emp_name
            updates["last_employee_name"] = emp_name

        # 4. Track Department
        dept = params.get("department_id") or params.get("department")
        if not dept and isinstance(data.get("raw_tool_result"), dict):
            raw_data = data["raw_tool_result"].get("data")
            if isinstance(raw_data, dict):
                dept = raw_data.get("department_name") or raw_data.get("department_id")
        if dept:
            updates[LAST_DEPARTMENT] = dept
            updates["last_department"] = dept

        if updates:
            self._store.update_user_context(user_id, updates)
            if agent and agent not in ["root_agent", "root", "chat_service", "system"]:
                self._store.update_agent_context(user_id, agent, updates)


# Singleton dùng chung trong toàn bộ Chat API
memory_store = ChatbotMemoryAdapter()
