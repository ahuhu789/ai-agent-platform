"""Interactive CLI Chat to test Multi-Agent Platform (Root Agent -> Hiring, Attendance, Employee)."""

import io
import os
import sys

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

from apps.chatbot.agent_setup import llm_provider, mcp_client, root_agent
from apps.chatbot.memory_store import memory_store
from shared.abstractions.agent import AgentRequest


def main():
    try:
        mcp_client.connect_all()
        run_chat_loop()
    finally:
        mcp_client.disconnect_all()


def run_chat_loop():
    print("=" * 70)
    print("AI AGENT PLATFORM - CHAT CLI INTERACTIVE")
    print("=" * 70)

    has_llm = llm_provider is not None and not getattr(llm_provider, "is_mock", False)
    if has_llm:
        print("[OK] Da ket noi LLM Provider thanh cong!")
    else:
        print("[INFO] He thong dang chay o che do [Rule-based & Template Formatter] thong minh.")
        print("       (Day du du lieu thuc te tu MCP Servers, khong ton chi phi API).")
        print("       -> Dien OPENAI_API_KEY vao file .env de kich hoat LLM sinh van tu nhien.")

    print("\nGoi y cau hoi thu nghiem:")
    print(" [Tuyển dụng]: 'Có bao nhiêu ứng viên đang chờ phỏng vấn?'")
    print(" [Tuyển dụng]: 'Danh sách các vị trí đang tuyển?'")
    print(" [Chuyên cần]: 'Tháng này nhân viên A đi làm bao nhiêu ngày?'")
    print(" [Nhân sự]:    'Nhân viên A thuộc phòng ban nào?'")
    print(" [Đa lượt]:    'Tháng này đi làm bao nhiêu ngày?' (Hệ thống tự nhớ Nhân viên A)")
    print("\n(Go 'exit' hoac 'quit' de thoat)")
    print("-" * 70)

    conv_id = memory_store.create_conversation(title="CLI Session", user_id="admin")
    user_id = "admin"

    while True:
        try:
            user_msg = input("\n[BAN]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nTam biet!")
            break

        if not user_msg:
            continue

        if user_msg.lower() in ["exit", "quit", "thoat"]:
            print("Tam biet!")
            break

        # Lưu tin nhắn user
        memory_store.save_message(conv_id, role="user", content=user_msg, user_id=user_id)
        chat_context = memory_store.build_chat_context(conv_id, user_id=user_id)

        req = AgentRequest(message=user_msg, conversation_id=conv_id, user_id=user_id, context=chat_context)
        res = root_agent.handle(req)

        intent = res.metadata.get("intent") or res.metadata.get("source") or "Unknown"
        tool_used = res.metadata.get("tool_used") or "None"
        mode = "LLM" if has_llm else "Rule-based"

        reply_text = ""
        if res.success and res.data:
            reply_text = res.data.get("response") or str(res.data)
        else:
            reply_text = res.error or "Khong co phan hoi."

        memory_store.save_message(conv_id, role="assistant", content=reply_text, metadata=res.metadata, user_id=user_id)
        memory_store.track_interaction(
            conversation_id=conv_id,
            user_id=user_id,
            user_message=user_msg,
            agent_response_data=res.data if isinstance(res.data, dict) else {},
            metadata=res.metadata,
        )

        print(f"\n[AI AGENT] [Phân hệ: {intent} | Tool: {tool_used} | Mode: {mode}]:")
        print(reply_text)
        print("-" * 70)


if __name__ == "__main__":
    main()
