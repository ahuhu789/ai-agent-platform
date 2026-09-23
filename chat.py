"""Interactive CLI Chat to test Hiring Agent with LLM API (OpenAI / DeepSeek / etc.)."""

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

from agents.hiring.hiring_agent import HiringAgent
from shared.abstractions.agent import AgentRequest


def main():
    agent = HiringAgent()

    print("=" * 70)
    print("[HIRING AGENT] - CHAT INTERACTIVE")
    print("=" * 70)

    if agent.openai_client:
        print("[OK] Da ket noi LLM API thanh cong!")
        print(f"   - Model: {agent.model_name}")
        print(f"   - Base URL: {os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')}")
    else:
        print("[INFO] Chua co OPENAI_API_KEY trong file .env.")
        print("   Agent dang chay o che do [Rule-based Fallback] thong minh.")
        print("   -> Dien OPENAI_API_KEY vao file .env de kich hoat LLM.")

    print("\nGoi y cau hoi:")
    print(" - Co bao nhieu ung vien dang cho phong van?")
    print(" - Danh sach cac vi tri dang tuyen?")
    print(" - Cho toi xem thong tin ung vien co ma UV001")
    print(" - Lich phong van tuan nay?")
    print(" - Bao cao tong quan tinh hinh tuyen dung")
    print("\n(Go 'exit' hoac 'quit' de thoat)")
    print("-" * 70)

    conv_id = "cli_session_1"
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

        req = AgentRequest(message=user_msg, conversation_id=conv_id, user_id=user_id)
        res = agent.handle(req)

        tool_used = res.metadata.get("tool_used") or "None"
        mode = "LLM" if agent.openai_client else "Rule-based"

        print(f"\n[AGENT] [{mode} | Tool: {tool_used}]:")
        print(res.data.get("response", res.error or "Khong co phan hoi."))
        print("-" * 70)


if __name__ == "__main__":
    main()
