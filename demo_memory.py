"""Demo: "Tìm nhân viên Nguyễn Văn A" -> "Tháng này người đó đi làm bao nhiêu ngày?"

Chạy:  python demo_memory.py
"""
from shared.memory import Message, create_memory_store
from shared.memory import context_keys as K

store = create_memory_store()  # mặc định in_memory, đổi bằng MEMORY_PROVIDER=redis
user = "U001"
conversation = store.create_conversation(user)

# Lượt 1: Employee Agent xử lý và ghi nhớ nhân viên vừa được nhắc tới
store.append_message(conversation.conversation_id, Message("user", "Tìm nhân viên Nguyễn Văn A"), user_id=user)
store.append_message(conversation.conversation_id, Message("assistant", "Đã tìm thấy NV001", agent_name="employee"), user_id=user)
store.update_user_context(user, {K.LAST_EMPLOYEE_ID: "NV001", K.LAST_EMPLOYEE_NAME: "Nguyễn Văn A"})

# Lượt 2: Attendance Agent đọc context chung để hiểu "người đó"
store.append_message(conversation.conversation_id, Message("user", "Tháng này người đó đi làm bao nhiêu ngày?"), user_id=user)
ctx = store.get_user_context(user)
print("Người đó là:", ctx[K.LAST_EMPLOYEE_NAME], f"({ctx[K.LAST_EMPLOYEE_ID]})")

# Context riêng của Attendance Agent
store.update_agent_context(user, "attendance", {K.LAST_MONTH: "2026-09"})
print("Attendance context:", store.get_agent_context(user, "attendance"))
print("Employee context  :", store.get_agent_context(user, "employee"))  # rỗng: tách theo agent

print("History gửi LLM   :", [m.content for m in store.get_history(conversation.conversation_id, limit=10, user_id=user)])
print("Conversations     :", [s.conversation_id for s in store.list_conversations(user)])
