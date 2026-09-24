import os
import sys
import json
import subprocess
import threading
from typing import Dict, Any, Optional

class MCPClient:
    """
    Client kết nối với Attendance MCP Server chạy dưới dạng subprocess.
    Truyền thông bằng giao thức JSON-RPC qua stdin/stdout.
    """
    def __init__(self, server_script_path: Optional[str] = None):
        if server_script_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            self.server_script_path = os.path.join(current_dir, "mcp_server.py")
        else:
            self.server_script_path = server_script_path
            
        self.process: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.request_id = 0
        
    def start(self):
        """
        Khởi chạy subprocess MCP Server.
        """
        with self.lock:
            if self.process and self.process.poll() is None:
                # Tiến trình đang chạy bình thường
                return
                
            cmd = [sys.executable, self.server_script_path]
            
            # Sử dụng utf-8 cho truyền thông tin
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=sys.stderr, # Cho phép log debug ghi trực tiếp ra stderr của terminal
                text=True,
                encoding="utf-8",
                bufsize=1 # Line buffered
            )
            
            # Đọc dòng đầu tiên/test connection nếu cần (tùy ý)
            # Server của chúng ta không ghi gì ra stdout khi bắt đầu cho đến khi có request.

    def stop(self):
        """
        Đóng kết nối và dừng subprocess MCP Server.
        """
        with self.lock:
            if self.process:
                if self.process.poll() is None:
                    try:
                        self.process.stdin.close()
                    except Exception:
                        pass
                    try:
                        self.process.terminate()
                        self.process.wait(timeout=3)
                    except Exception:
                        try:
                            self.process.kill()
                        except Exception:
                            pass
                self.process = None

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gọi tool thông qua MCP Server bằng tin nhắn JSON-RPC.
        """
        self.start()  # Đảm bảo server đang chạy
        
        with self.lock:
            self.request_id += 1
            current_id = self.request_id
            
            # Tạo tin nhắn JSON-RPC tools/call
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": name,
                    "arguments": arguments
                },
                "id": current_id
            }
            
            try:
                # Gửi payload kèm ký tự xuống dòng
                payload_str = json.dumps(payload, ensure_ascii=False)
                self.process.stdin.write(payload_str + "\n")
                self.process.stdin.flush()
                
                # Đọc dòng phản hồi từ stdout
                response_str = self.process.stdout.readline()
                if not response_str:
                    raise ConnectionError("MCP Server subprocess đã dừng đột ngột hoặc đóng stdout.")
                    
                response = json.loads(response_str.strip())
                
                # Kiểm tra lỗi JSON-RPC
                if "error" in response:
                    err = response["error"]
                    raise RuntimeError(f"MCP RPC Error [{err.get('code')}]: {err.get('message')}")
                    
                result = response.get("result", {})
                content = result.get("content", [])
                
                # Giải nén kết quả text trong content
                if not content or content[0].get("type") != "text":
                    raise ValueError("MCP Server phản hồi định dạng content không hợp lệ.")
                    
                # Parse kết quả thô của tool (chuỗi JSON) trả về dict
                tool_output_str = content[0].get("text")
                return json.loads(tool_output_str)
                
            except Exception as e:
                # Reset tiến trình nếu gặp lỗi truyền thông để khởi động lại ở lần gọi sau
                if self.process:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                    self.process = None
                raise RuntimeError(f"Lỗi khi giao tiếp với MCP Server: {e}")

    def list_tools(self) -> list:
        """
        Lấy danh sách các tool và schema được đăng ký trên MCP Server qua giao thức JSON-RPC method 'tools/list'.
        """
        self.start()  # Đảm bảo server đang chạy
        
        with self.lock:
            self.request_id += 1
            current_id = self.request_id
            
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": current_id
            }
            
            try:
                payload_str = json.dumps(payload, ensure_ascii=False)
                self.process.stdin.write(payload_str + "\n")
                self.process.stdin.flush()
                
                response_str = self.process.stdout.readline()
                if not response_str:
                    raise ConnectionError("MCP Server subprocess đã dừng đột ngột hoặc đóng stdout.")
                    
                response = json.loads(response_str.strip())
                if "error" in response:
                    err = response["error"]
                    raise RuntimeError(f"MCP RPC Error [{err.get('code')}]: {err.get('message')}")
                    
                result = response.get("result", {})
                return result.get("tools", [])
                
            except Exception as e:
                if self.process:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                    self.process = None
                raise RuntimeError(f"Lỗi khi lấy danh sách tool từ MCP Server: {e}")

    def __del__(self):
        try:
            self.stop()
        except Exception:
            pass

