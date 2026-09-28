"""Tạo các file PDF mẫu phong phú để kiểm thử tính năng OCR & đọc tài liệu."""
import os
import sys
import io

# Ensure UTF-8 output on Windows console
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pymupdf
from PIL import Image, ImageDraw, ImageFont

SAMPLES_DIR = os.path.join(os.path.dirname(__file__), "..", "samples")
os.makedirs(SAMPLES_DIR, exist_ok=True)

FONT_PATH = "C:/Windows/Fonts/arial.ttf"
FONT_BOLD_PATH = "C:/Windows/Fonts/arialbd.ttf"
if not os.path.exists(FONT_BOLD_PATH):
    FONT_BOLD_PATH = FONT_PATH


def create_hop_dong_lao_dong_pdf():
    """Tạo file PDF hợp đồng lao động chuẩn (Digital PDF đa trang)."""
    doc = pymupdf.open()
    
    # Trang 1
    page1 = doc.new_page(width=595, height=842) # A4
    text_p1 = (
        "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\n"
        "Độc lập - Tự do - Hạnh phúc\n"
        "------------------o0o------------------\n\n"
        "HỢP ĐỒNG LAO ĐỘNG\n"
        "Số: 88/2026/HĐLĐ-FME\n\n"
        "Hôm nay, ngày 01 tháng 09 năm 2026, tại văn phòng Công ty Cổ phần Công nghệ FME, chúng tôi gồm:\n\n"
        "BÊN A: NGƯỜI SỬ DỤNG LAO ĐỘNG\n"
        "- Tên doanh nghiệp: CÔNG TY CỔ PHẦN CÔNG NGHỆ FME\n"
        "- Đại diện bởi: Ông Trần Minh Tuấn\n"
        "- Chức vụ: Giám đốc Điều hành\n"
        "- Địa chỉ: Tầng 12, Tòa nhà FME Tower, Quận Cầu Giấy, Hà Nội\n"
        "- Mã số thuế: 0108998877\n\n"
        "BÊN B: NGƯỜI LAO ĐỘNG\n"
        "- Họ và tên: BÀ LÊ THỊ MAI ANH\n"
        "- Ngày sinh: 15/04/1996\n"
        "- Số CCCD: 001196008899\n"
        "- Trình độ: Thạc sĩ Khoa học Dữ liệu\n"
        "- Địa chỉ thường trú: Phường Dịch Vọng Hậu, Quận Cầu Giấy, Hà Nội\n\n"
        "Hai bên cùng thỏa thuận và thống nhất ký kết hợp đồng lao động với các điều khoản như sau:\n\n"
        "ĐIỀU 1: THỜI HẠN VÀ CÔNG VIỆC HỢP ĐỒNG\n"
        "- Loại hợp đồng: Hợp đồng lao động xác định thời hạn 12 tháng.\n"
        "- Thời gian hiệu lực: Từ ngày 01/09/2026 đến hết ngày 31/08/2027.\n"
        "- Vị trí chuyên môn: Chuyên viên Phân tích Dữ liệu Cao cấp (Senior Data Analyst).\n"
        "- Bộ phận công tác: Trung tâm Nghiên cứu Trí tuệ Nhân tạo & Dữ liệu FME."
    )
    rect1 = pymupdf.Rect(50, 45, 545, 800)
    page1.insert_textbox(rect1, text_p1, fontname="arial", fontfile=FONT_PATH, fontsize=11, lineheight=1.35)
    
    # Trang 2
    page2 = doc.new_page(width=595, height=842)
    text_p2 = (
        "ĐIỀU 2: CHẾ ĐỘ LÀM VIỆC VÀ QUYỀN LỢI\n"
        "- Thời gian làm việc: 40 giờ/tuần (Từ Thứ 2 đến Thứ 6, từ 08:30 đến 17:30).\n"
        "- Mức lương chính: 28.500.000 VNĐ / tháng (Hai mươi tám triệu năm trăm nghìn đồng).\n"
        "- Phụ cấp ăn trưa: 1.200.000 VNĐ / tháng.\n"
        "- Phụ cấp chuyên cần & hiệu quả công việc: Theo quy chế tài chính của công ty.\n"
        "- Hình thức trả lương: Chuyển khoản ngân hàng vào ngày 05 hàng tháng.\n"
        "- Chế độ bảo hiểm: Được đóng đầy đủ BHXH, BHYT, BHTN theo quy định pháp luật.\n"
        "- Chế độ nghỉ phép: 12 ngày phép năm hưởng nguyên lương.\n\n"
        "ĐIỀU 3: NGHĨA VỤ CỦA NGƯỜI LAO ĐỘNG\n"
        "- Hoàn thành tốt các nhiệm vụ được giao theo bản mô tả công việc.\n"
        "- Tuân thủ quy định bảo mật thông tin, tài sản trí tuệ và bí mật kinh doanh của công ty.\n"
        "- Chấp hành nghiêm chỉnh nội quy lao động và quy tắc văn hóa ứng xử FME.\n\n"
        "ĐIỀU 4: ĐIỀU KHOẢN THI HÀNH\n"
        "Hợp đồng này được lập thành 02 bản có giá trị pháp lý như nhau, mỗi bên giữ 01 bản.\n\n"
        "            ĐẠI DIỆN BÊN A                                          ĐẠI DIỆN BÊN B\n"
        "              (Đã ký & đóng dấu)                                          (Đã ký & ghi rõ họ tên)\n\n\n"
        "              Trần Minh Tuấn                                          Lê Thị Mai Anh"
    )
    rect2 = pymupdf.Rect(50, 50, 545, 800)
    page2.insert_textbox(rect2, text_p2, fontname="arial", fontfile=FONT_PATH, fontsize=11, lineheight=1.35)
    
    out_path = os.path.join(SAMPLES_DIR, "sample_hop_dong_lao_dong.pdf")
    doc.save(out_path)
    doc.close()
    print(f"✓ Đã tạo: {out_path}")


def create_bang_cham_cong_pdf():
    """Tạo file PDF bảng chấm công & chuyên cần tháng 8/2026."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    
    content = (
        "CÔNG TY CỔ PHẦN CÔNG NGHỆ FME\n"
        "PHÒNG QUẢN TRỊ NGUỒN NHÂN LỰC\n"
        "-------------------------------------\n\n"
        "BẢNG BÁO CÁO TỔNG HỢP CHUYÊN CẦN THÁNG 08/2026\n\n"
        "Kính gửi: Ban Giám đốc Công ty\n"
        "Người lập báo cáo: Bộ phận Chấm công & Tiền lương\n"
        "Kỳ tính công: Từ ngày 01/08/2026 đến hết ngày 31/08/2026\n\n"
        "1. TỔNG QUAN TÌNH HÌNH CHUYÊN CẦN TOÀN CÔNG TY:\n"
        "- Tổng số nhân sự: 45 nhân viên\n"
        "- Tổng số ngày làm việc chuẩn trong tháng: 22 ngày\n"
        "- Tỷ lệ đi làm đúng giờ toàn công ty: 94.6%\n"
        "- Tổng số giờ tăng ca (OT): 186 giờ\n\n"
        "2. THỐNG KÊ CHI TIẾT THEO TỪNG NHÂN SỰ:\n"
        "----------------------------------------------------------------------------------------------------\n"
        "STT | Mã NV  | Họ và Tên         | Phòng Ban   | Ngày công | Đi trễ | Về sớm | Phép năm | Tăng ca\n"
        "----------------------------------------------------------------------------------------------------\n"
        "01  | NV001  | Nguyễn Văn A      | Kỹ thuật    | 22/22     | 0 lần  | 0 lần  | 0 ngày   | 14.5 giờ\n"
        "02  | NV002  | Trần Thị B        | Nhân sự     | 21/22     | 2 lần  | 0 lần  | 1 ngày   | 0.0 giờ\n"
        "03  | NV003  | Lê Văn C          | Kinh doanh  | 20/22     | 3 lần  | 1 lần  | 2 ngày   | 8.0 giờ\n"
        "04  | NV004  | Phạm Thị D        | Marketing   | 22/22     | 1 lần  | 0 lần  | 0 ngày   | 6.0 giờ\n"
        "05  | NV005  | Hoàng Văn E       | Kỹ thuật    | 22/22     | 0 lần  | 0 lần  | 0 ngày   | 18.0 giờ\n"
        "----------------------------------------------------------------------------------------------------\n\n"
        "3. ĐÁNH GIÁ VÀ ĐỀ XUẤT KHEN THƯỞNG:\n"
        "- Nhân viên chuyên cần xuất sắc nhất: Nguyễn Văn A (NV001) và Hoàng Văn E (NV005) - Đạt 100% công, không đi trễ.\n"
        "- Trường hợp cần nhắc nhở cải thiện: Lê Văn C (NV003) - Đi trễ 3 lần tổng cộng 45 phút trong tháng.\n\n"
        "Hà Nội, ngày 31 tháng 08 năm 2026\n"
        "Trưởng phòng Nhân sự: Nguyễn Thùy Linh (Đã duyệt)"
    )
    rect = pymupdf.Rect(45, 45, 550, 800)
    page.insert_textbox(rect, content, fontname="arial", fontfile=FONT_PATH, fontsize=10.5, lineheight=1.3)
    
    out_path = os.path.join(SAMPLES_DIR, "sample_bang_cham_cong_thang_8.pdf")
    doc.save(out_path)
    doc.close()
    print(f"✓ Đã tạo: {out_path}")


def create_don_xin_nghi_phep_scan_pdf():
    """Tạo file PDF giả lập bản scan (ảnh hóa đơn / đơn từ được nhúng vào PDF để test OCR scan)."""
    # Tạo ảnh trắng 1200 x 1600 giả lập tờ A4 scan 150 DPI
    img = Image.new("RGB", (1200, 1600), color=(252, 252, 250))
    draw = ImageDraw.Draw(img)
    
    font_large = ImageFont.truetype(FONT_BOLD_PATH, 32)
    font_title = ImageFont.truetype(FONT_BOLD_PATH, 28)
    font_regular = ImageFont.truetype(FONT_PATH, 24)
    font_small = ImageFont.truetype(FONT_PATH, 20)
    
    # Header
    draw.text((360, 80), "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", fill=(30, 30, 30), font=font_title)
    draw.text((450, 125), "Độc lập - Tự do - Hạnh phúc", fill=(30, 30, 30), font=font_regular)
    draw.line([(430, 165), (770, 165)], fill=(50, 50, 50), width=2)
    
    # Title
    draw.text((420, 240), "ĐƠN XIN NGHỈ PHÉP NĂM", fill=(10, 10, 10), font=font_large)
    draw.text((350, 320), "Kính gửi: Ban Giám đốc Công ty Cổ phần Công nghệ FME", fill=(40, 40, 40), font=font_regular)
    draw.text((450, 360), "Đồng kính gửi: Phòng Quản trị Nguồn Nhân lực", fill=(40, 40, 40), font=font_regular)
    
    # Body lines
    lines = [
        "Tôi tên là: Đặng Quốc Bảo",
        "Mã số nhân viên: NV008",
        "Chức danh / Vị trí: Kỹ sư Phần mềm Backend (Software Engineer)",
        "Bộ phận công tác: Khối Kỹ thuật và Công nghệ",
        "",
        "Nay tôi làm đơn này kính xin Ban Giám đốc và Trưởng bộ phận cho phép tôi được nghỉ phép:",
        "- Số ngày xin nghỉ: 03 ngày làm việc",
        "- Thời gian nghỉ: Từ ngày 20/09/2026 đến hết ngày 22/09/2026",
        "- Lý do xin nghỉ: Giải quyết việc hiếu hỉ của gia đình tại quê nhà",
        "",
        "- Người tiếp nhận bàn giao công việc: Nguyễn Văn A (Mã NV: NV001)",
        "- Nội dung bàn giao: Tiến độ phát hành tính năng OCR Module và MCP Attendance Server",
        "- Phương thức liên hệ khẩn cấp khi có việc gấp: Số điện thoại 0912.345.678",
        "",
        "Tôi cam kết sẽ hoàn thành đầy đủ mọi công việc tồn đọng ngay sau khi quay trở lại làm việc.",
        "Kính mong Ban Giám đốc xem xét và phê duyệt đơn xin nghỉ phép của tôi.",
        "Tôi xin chân thành cảm ơn!"
    ]
    
    y = 440
    for line in lines:
        if line:
            draw.text((120, y), line, fill=(30, 30, 30), font=font_regular)
        y += 42
        
    # Signatures
    draw.text((700, 1220), "Hà Nội, ngày 18 tháng 09 năm 2026", fill=(40, 40, 40), font=font_small)
    draw.text((750, 1260), "NGƯỜI LÀM ĐƠN", fill=(20, 20, 20), font=font_title)
    draw.text((760, 1310), "(Ký và ghi rõ họ tên)", fill=(80, 80, 80), font=font_small)
    draw.text((780, 1420), "Đặng Quốc Bảo", fill=(10, 10, 10), font=font_title)
    
    draw.text((180, 1260), "Ý KIẾN TRƯỞNG BỘ PHẬN", fill=(20, 20, 20), font=font_title)
    draw.text((220, 1310), "Đồng ý cho nghỉ phép", fill=(20, 20, 160), font=font_regular)
    draw.text((240, 1420), "Trần Minh Tuấn", fill=(10, 10, 10), font=font_title)
    
    # Thêm viền nhẹ giả lập trang scan
    draw.rectangle([(20, 20), (1180, 1580)], outline=(220, 220, 215), width=2)
    
    # Lưu vào buffer PNG
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    
    # Tạo PDF từ ảnh scan
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.getvalue())
    
    out_path = os.path.join(SAMPLES_DIR, "sample_don_xin_nghi_phep_scan.pdf")
    doc.save(out_path)
    doc.close()
    print(f"✓ Đã tạo: {out_path}")


if __name__ == "__main__":
    print("🚀 Bắt đầu tạo các file PDF mẫu...")
    create_hop_dong_lao_dong_pdf()
    create_bang_cham_cong_pdf()
    create_don_xin_nghi_phep_scan_pdf()
    print("✨ Hoàn thành tạo tất cả file mẫu trong thư mục 'samples/'!")
