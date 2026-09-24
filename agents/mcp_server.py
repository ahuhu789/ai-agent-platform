import os
import sys
import json
from datetime import datetime

# Set output encoding to UTF-8 to prevent character encoding issues on Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

def log_debug(message: str):
    """
    Log debug messages to stderr so they don't corrupt the JSON-RPC stdout stream.
    """
    sys.stderr.write(f"[MCP SERVER DEBUG] {message}\n")
    sys.stderr.flush()

from integrations.my_enterprise_attendance.repository import get_repository

def load_mock_data():
    """
    Backward compatible helper returning repository in-memory state.
    """
    repo = get_repository()
    return {
        "employees": repo.get_all_employees(),
        "attendance_records": repo.get_all_records()
    }

# --- TOOL IMPLEMENTATIONS ---

def get_attendance_history(employee_id: str, from_date: str, to_date: str) -> dict:
    emp_id = str(employee_id).strip().upper() if employee_id else ""
    log_debug(f"Executing get_attendance_history: {emp_id} ({from_date} to {to_date})")
    repo = get_repository()
    return repo.get_attendance_history(employee_id=emp_id, from_date=from_date, to_date=to_date)

def get_employee_attendance(employee_id: str) -> dict:
    emp_id = str(employee_id).strip().upper() if employee_id else ""
    log_debug(f"Executing get_employee_attendance: {emp_id}")
    repo = get_repository()
    return repo.get_employee_attendance(employee_id=emp_id)

def get_monthly_attendance_statistics(month: int, year: int) -> dict:
    log_debug(f"Executing get_monthly_attendance_statistics: {month}/{year}")
    repo = get_repository()
    return repo.get_monthly_attendance_statistics(month=month, year=year)

def get_late_arrival_summary(employee_id: str) -> dict:
    emp_id = str(employee_id).strip().upper() if employee_id else ""
    log_debug(f"Executing get_late_arrival_summary: {emp_id}")
    repo = get_repository()
    return repo.get_late_arrival_summary(employee_id=emp_id)

def get_absence_summary(employee_id: str) -> dict:
    emp_id = str(employee_id).strip().upper() if employee_id else ""
    log_debug(f"Executing get_absence_summary: {emp_id}")
    repo = get_repository()
    return repo.get_absence_summary(employee_id=emp_id)

def get_employee_list() -> dict:
    log_debug("Executing get_employee_list")
    repo = get_repository()
    return repo.get_employee_list()

def get_daily_attendance(date: str = None) -> dict:
    log_debug(f"Executing get_daily_attendance: {date}")
    repo = get_repository()
    return repo.get_daily_attendance(target_date=date)

# --- JSON-RPC CONTROLLER ---

def handle_rpc_request(request_str: str) -> str:
    try:
        req = json.loads(request_str)
    except Exception as e:
        return json.dumps({
            "jsonrpc": "2.0",
            "error": {"code": -32700, "message": f"Parse error: {e}"},
            "id": None
        })
        
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params", {})
    
    if method == "tools/list":
        # Trả về danh sách tool có sẵn
        tools = [
            {
                "name": "get_attendance_history",
                "description": "Lấy danh sách lịch sử chuyên cần chi tiết của một nhân viên trong khoảng thời gian xác định.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {"type": "string", "description": "Mã nhân viên (ví dụ: 009, 001, 010)"},
                        "from_date": {"type": "string", "description": "Ngày bắt đầu tìm kiếm (YYYY-MM-DD)"},
                        "to_date": {"type": "string", "description": "Ngày kết thúc tìm kiếm (YYYY-MM-DD)"}
                    },
                    "required": ["employee_id", "from_date", "to_date"]
                }
            },
            {
                "name": "get_employee_attendance",
                "description": "Xem thông tin tóm tắt chuyên cần và các bản ghi chấm công gần đây của một nhân viên.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {"type": "string", "description": "Mã nhân viên (ví dụ: 009, 001, 010)"}
                    },
                    "required": ["employee_id"]
                }
            },
            {
                "name": "get_monthly_attendance_statistics",
                "description": "Xem thống kê tổng quan và chi tiết chuyên cần của tất cả nhân viên trong một tháng cụ thể.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "month": {"type": "integer", "description": "Tháng thống kê (1-12)"},
                        "year": {"type": "integer", "description": "Năm thống kê (ví dụ: 2026)"}
                    },
                    "required": ["month", "year"]
                }
            },
            {
                "name": "get_late_arrival_summary",
                "description": "Xem tóm tắt và chi tiết các lần đi muộn/đi trễ của một nhân viên.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {"type": "string", "description": "Mã nhân viên (ví dụ: 009, 001)"}
                    },
                    "required": ["employee_id"]
                }
            },
            {
                "name": "get_absence_summary",
                "description": "Xem tóm tắt và chi tiết các ngày vắng có phép hoặc không phép của một nhân viên.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "employee_id": {"type": "string", "description": "Mã nhân viên (ví dụ: 009, 001)"}
                    },
                    "required": ["employee_id"]
                }
            },
            {
                "name": "get_employee_list",
                "description": "Xem danh sách và danh bạ toàn bộ nhân viên trong công ty (mã nhân viên, họ tên, chức vụ, phòng ban).",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "get_daily_attendance",
                "description": "Xem danh sách và tình hình chấm công của toàn bộ nhân viên công ty trong ngày hôm nay hoặc theo ngày cụ thể (ai đi làm, ai đúng giờ, ai đi muộn, ai vắng phép).",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Ngày cần tra cứu (YYYY-MM-DD hoặc 'hôm nay')"}
                    }
                }
            }
        ]
        return json.dumps({
            "jsonrpc": "2.0",
            "result": {"tools": tools},
            "id": req_id
        }, ensure_ascii=False)
        
    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        try:
            if tool_name == "get_attendance_history":
                res_data = get_attendance_history(
                    employee_id=arguments.get("employee_id"),
                    from_date=arguments.get("from_date"),
                    to_date=arguments.get("to_date")
                )
            elif tool_name == "get_employee_attendance":
                res_data = get_employee_attendance(
                    employee_id=arguments.get("employee_id")
                )
            elif tool_name in ("get_monthly_attendance_statistics", "get_monthly_attendance", "get_attendance_statistics"):
                res_data = get_monthly_attendance_statistics(
                    month=arguments.get("month"),
                    year=arguments.get("year")
                )
            elif tool_name == "get_late_arrival_summary":
                res_data = get_late_arrival_summary(
                    employee_id=arguments.get("employee_id")
                )
            elif tool_name == "get_absence_summary":
                res_data = get_absence_summary(
                    employee_id=arguments.get("employee_id")
                )
            elif tool_name in ("get_employee_list", "list_employees"):
                res_data = get_employee_list()
            elif tool_name in ("get_daily_attendance", "daily_attendance"):
                res_data = get_daily_attendance(
                    date=arguments.get("date")
                )
            else:
                return json.dumps({
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {tool_name}"},
                    "id": req_id
                })
                
            # Đóng gói result theo format của MCP
            return json.dumps({
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(res_data, ensure_ascii=False)
                        }
                    ]
                },
                "id": req_id
            }, ensure_ascii=False)
            
        except Exception as err:
            log_debug(f"Error executing tool {tool_name}: {err}")
            return json.dumps({
                "jsonrpc": "2.0",
                "error": {"code": -32000, "message": str(err)},
                "id": req_id
            })
            
    else:
        return json.dumps({
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method not found: {method}"},
            "id": req_id
        })

def main():
    log_debug("MCP Server started, listening for JSON-RPC requests on stdin...")
    
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                # EOF reached, terminate server
                log_debug("Stdin closed (EOF). Exiting.")
                break
                
            line = line.strip()
            if not line:
                continue
                
            # Xử lý RPC request
            response_json = handle_rpc_request(line)
            
            # Ghi kết quả ra stdout
            sys.stdout.write(response_json + "\n")
            sys.stdout.flush()
            
        except KeyboardInterrupt:
            log_debug("KeyboardInterrupt. Exiting.")
            break
        except Exception as e:
            log_debug(f"Fatal error in server loop: {e}")
            break

if __name__ == "__main__":
    main()
