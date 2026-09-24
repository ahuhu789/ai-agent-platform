# My Enterprise Attendance & Employee Integration Module (Web 1.18)

Phân hệ tích hợp độc lập dành cho **My Enterprise Web 1.18**, phục vụ:
1. Trích xuất danh sách nhân viên thực tế từ Employee API.
2. Xác định mã nhân viên hiển thị (`codeDisplay`) làm mã định danh thống nhất.
3. Phân loại và khám phá API Chấm công (Attendance API).
4. Thực hiện JOIN giữa Employee và Attendance bằng `id` để tạo Dataset chuẩn hóa.
5. Cung cấp tầng dữ liệu trừu tượng (`AttendanceRepository`) cho **Attendance MCP Server** với hai chế độ: `mock` (mặc định demo ngoại tuyến) và `real` (kết nối API thật qua VPN).

---

## 1. Kiến Trúc Tích Hợp (Architecture)

```text
                    My Enterprise Web 1.18
                              |
             +----------------+----------------+
             |                                 |
             ↓                                 ↓
       Employee API                       Attendance API
             |                                 |
             ↓                                 ↓
      Employee Dataset                 Attendance Dataset
             |                                 |
             +------------- JOIN --------------+
                            |
                            ↓
                  Normalized Attendance
                            |
                            ↓
                   Attendance Repository
                            |
                            ↓
                     Attendance MCP
                            |
                            ↓
                    Attendance Agent
```

---

## 2. Thông Tin Endpoint API Thực Tế

### 2.1. Employee API (Danh sách nhân viên)
- **Phương thức:** `GET`
- **Host mặc định:** `https://fm-internal.tasolutions.com.vn:8444`
- **Đường dẫn:** `/api/core/core/api/v1/resources/organization/org-info/employees/suggestion`
- **Query Parameters:**
  - `size`: Số bản ghi mỗi trang (mặc định: `100`).
  - `page`: Trang hiện tại (bắt đầu từ `0`).
  - `searchText`: Từ khóa tìm kiếm (tùy chọn).
- **Ví dụ Request:**
  ```http
  GET /api/core/core/api/v1/resources/organization/org-info/employees/suggestion?size=100&page=0&searchText= HTTP/1.1
  Host: fm-internal.tasolutions.com.vn:8444
  Authorization: Bearer <MY_ENTERPRISE_TOKEN>
  Accept: application/json
  ```
- **Phân trang:** Client tự động kiểm tra metadata (`total`, `totalElements`, `totalPages`, `hasNext`) hoặc lặp `page=0, 1, 2...` cho tới khi `results == []` hoặc `len(results) < size`.

### 2.2. Attendance API (Chấm công)
- **Phương thức:** `GET`
- **Đường dẫn:** `/api/core/core/api/v1/resources/employees/attendances/me`
- **Query Parameters:**
  - `monthYear`: Ngày hoặc tháng cần tra cứu (`YYYY-MM-DD` hoặc `YYYY-MM`).
  - `page`: Trang hiện tại (mặc định: `0`).
  - `size`: Số bản ghi mỗi trang (mặc định: `50`).

> [!CAUTION]
> **CẢNH BÁO QUAN TRỌNG VỀ PHẠM VI ATTENDANCE API:**
> - Endpoint `/resources/employees/attendances/me` thuộc **TYPE A (Current User)**: chỉ phản ánh dữ liệu chấm công của tài khoản đăng nhập hiện tại.
> - **Attendance all-employee endpoint has not yet been verified from Web 1.18 Network and must not be assumed.**
> - Nếu cần lấy chấm công toàn công ty từ API thật, lập trình viên cần bắt gói tin DevTools Network trên Web 1.18 khi người quản lý mở bảng chấm công để ghi nhận endpoint chính thức.

---

## 3. Quy Chuẩn Ánh Xạ Dữ Liệu (Mapping & JOIN)

### 3.1. Employee Schema
Dữ liệu thô từ API:
```json
{
  "id": 16,
  "firstName": "Vy",
  "lastName": "Lê Hữu Thanh",
  "codeDisplay": "009"
}
```
Sau khi chuẩn hóa qua `normalize_employee`:
- `id` $\rightarrow$ `employee_id`: `16`
- `codeDisplay` $\rightarrow$ `employee_code`: `"009"` (QUAN TRỌNG: BẮT BUỘC dùng `codeDisplay`, **KHÔNG** dùng `id`, **KHÔNG** tự sinh)
- `firstName` $\rightarrow$ `first_name`: `"Vy"`
- `lastName` $\rightarrow$ `last_name`: `"Lê Hữu Thanh"`
- Ghép họ tên $\rightarrow$ `employee_name`: `"Lê Hữu Thanh Vy"`

### 3.2. Attendance Schema
Dữ liệu thô từ Web 1.18:
```json
{
  "employeeInfo": {
    "id": 16,
    "firstName": "Vy",
    "lastName": "Lê Hữu Thanh",
    "codeDisplay": "009"
  },
  "recordDate": "2026-07-28",
  "recordTime": "10:19:49",
  "checkInTime": "10:19:49",
  "checkOutTime": "21:19:57",
  "latitude": 10.807207964,
  "longitude": 106.628620666,
  "locationName": "Phường Tân Sơn Nhì, Tân Phú, TP.HCM"
}
```

### 3.3. Quy tắc JOIN: Employee + Attendance
- **Khóa JOIN duy nhất:** `attendance.employeeInfo.id == employee.id`
- **Sau JOIN:** `employee_code = employee.codeDisplay`
- **Nguyên tắc an toàn:**
  - TUYỆT ĐỐI KHÔNG JOIN bằng `firstName`, `lastName` hoặc so khớp mờ (fuzzy match).
  - Nếu `employeeInfo.id` không tồn tại trong danh sách nhân viên: đánh dấu `unmapped = True`, ghi log cảnh báo và không làm crash hệ thống.

---

## 4. Cấu Hình Nguồn Dữ Liệu (`ATTENDANCE_DATA_SOURCE`)

Hệ thống hỗ trợ 2 chế độ độc lập qua biến môi trường:

```env
# Chế độ 'mock' (Mặc định - chạy offline, không phụ thuộc VPN/token)
ATTENDANCE_DATA_SOURCE=mock

# Chế độ 'real' (Khi kết nối mạng nội bộ/VPN và có MY_ENTERPRISE_TOKEN)
ATTENDANCE_DATA_SOURCE=real
```

### Cách thức hoạt động của `AttendanceRepository`:
- **Chế độ MOCK:**
  - Nạp dữ liệu từ `fixtures/employees_mock.json` và `fixtures/attendance_mock.json` (tổng hợp 7 nhân viên synthetic với đầy đủ các kịch bản: đúng giờ, đi muộn, vắng có phép, vắng không phép, và nhân viên chưa có bản ghi nào).
  - Bảo tồn tính tương thích ngược với `data/mock_attendance.json`.
- **Chế độ REAL:**
  - Sử dụng `EmployeeClient` và `AttendanceClient` gọi API thật.
  - Tự động lưu cache snapshot vào `data/local/` (được `.gitignore` bảo vệ).
  - Nếu gặp sự cố mất kết nối VPN hoặc token hết hạn, hệ thống tự động fallback an toàn về dữ liệu Mock offline mà không làm crash MCP Server.

---

## 5. Hướng Dẫn Sử Dụng Command Line (CLI) Crawl

Module cung cấp CLI độc lập để crawl và kiểm tra dữ liệu:

```powershell
# 1. Xem hướng dẫn cú pháp
.\venv\Scripts\python.exe -m integrations.my_enterprise_attendance.client --help

# 2. Crawl danh sách nhân viên
.\venv\Scripts\python.exe -m integrations.my_enterprise_attendance.client --employees

# 3. Crawl dữ liệu chấm công cá nhân tháng hiện tại
.\venv\Scripts\python.exe -m integrations.my_enterprise_attendance.client --attendance

# 4. Crawl toàn bộ và thực hiện JOIN
.\venv\Scripts\python.exe -m integrations.my_enterprise_attendance.client --all
```

**Định dạng kết quả in ra an toàn:**
```text
==================================================
   KẾT QUẢ TỔNG HỢP VÀ JOIN DỮ LIỆU
==================================================
Employee count: 120
Attendance record count: 45
Mapped attendance: 45
Unmapped attendance: 0
[LƯU TRỮ] Đã lưu normalized dataset vào data/local/attendance_normalized.json
==================================================
```

---

## 6. Cơ Chế An Toàn Bảo Mật (Security Guidelines)

- **Không hard-code token:** Token chỉ lấy từ biến môi trường `MY_ENTERPRISE_TOKEN`.
- **Không log token hoặc thông tin nhạy cảm:** Không in Authorization header, cookie, password. Phương thức `__repr__` của `MyEnterpriseConfig` tự động che giấu token thành `***REDACTED***`.
- **Chặn commit dữ liệu production:** Các thư mục lưu snapshot dữ liệu crawl thật (`data/local/`, `data/raw/`) đã được thêm vào `.gitignore`.

---

## 7. Kiểm Thử Hệ Thống (Automated Testing)

Toàn bộ unit tests chạy 100% OFFLINE bằng mocked HTTP, không cần mạng hay token thật:

```powershell
# Chạy toàn bộ 37 tests của phân hệ My Enterprise
.\venv\Scripts\pytest.exe integrations/my_enterprise_attendance/tests/ -v

# Chạy kiểm thử hồi quy toàn bộ Attendance MCP & Agent (24/24 tests passed)
.\venv\Scripts\pytest.exe tests/test_attendance.py -v
```
