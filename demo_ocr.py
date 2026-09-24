"""
Demo OCR Service Độc Lập (Standalone OCR Service Demo)
------------------------------------------------------
Demo này minh họa quy trình bóc tách ký tự từ hình ảnh bằng OCR Service độc lập.
HOÀN TOÀN KHÔNG PHỤ THUỘC VÀO:
- Attendance Agent
- Attendance MCP Server / Client
- Root Agent
- Query Router
- RAG Pipeline

Cách chạy:
    python demo_ocr.py                          # Chạy demo tự động với ảnh mẫu (Tiếng Anh + Tiếng Việt + Edge cases)
    python demo_ocr.py đường_dẫn_tới_ảnh.png    # Chạy OCR trên ảnh tùy chọn của bạn
"""

import os
import sys
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# Đảm bảo UTF-8 terminal trên Windows
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# Thêm thư mục gốc vào sys.path
ROOT_DIR = os.path.abspath(os.path.dirname(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ocr import (
    OCRService,
    ocr_service,
    OCROptions,
    OCRResult,
    OCRStatus
)

def create_sample_image(text: str, filename: str, width: int = 800, height: int = 160) -> str:
    """Tạo file ảnh mẫu sắc nét để demo."""
    temp_dir = tempfile.gettempdir()
    filepath = os.path.join(temp_dir, filename)
    
    img = Image.new("RGB", (width, height), color="white")
    draw = ImageDraw.Draw(img)
    
    font_path = r"C:\Windows\Fonts\arial.ttf"
    try:
        font = ImageFont.truetype(font_path, 28) if os.path.exists(font_path) else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
        
    draw.text((30, 60), text, fill="black", font=font)
    img.save(filepath)
    return filepath

def print_result_card(title: str, result: OCRResult):
    """Hiển thị kết quả OCR một cách trực quan, đẹp mắt."""
    print("\n" + "=" * 70)
    print(f" [DEMO] {title}")
    print("=" * 70)
    print(f"  • Trạng thái (Status) : {result.status.value.upper()}")
    print(f"  • Thời gian xử lý     : {result.metadata.duration_ms:.2f} ms")
    print(f"  • Kích thước ảnh      : {result.metadata.image_width}x{result.metadata.image_height} px")
    print(f"  • Định dạng           : {result.metadata.image_format or 'N/A'}")
    print(f"  • Ngôn ngữ OCR        : {result.metadata.language}")
    print(f"  • Tiền xử lý (Preproc): {'Có' if result.metadata.preprocessed else 'Không'}")
    print(f"  • Độ tự tin trung bình: {result.metadata.confidence if result.metadata.confidence is not None else 'N/A'}%")
    print(f"  • Số từ nhận diện     : {result.metadata.word_count}")
    print(f"  • Số ký tự            : {result.metadata.char_count}")
    
    if result.has_error:
        print(f"  • THÔNG BÁO LỖI       : {result.error_message}")
    else:
        print("\n  [NỘI DUNG VĂN BẢN TRÍCH XUẤT]:")
        print("  " + "-" * 66)
        for line in result.text.splitlines():
            print(f"    {line}")
        print("  " + "-" * 66)
        
    if result.words:
        print(f"\n  [CHI TIẾT {min(len(result.words), 5)} TỪ ĐẦU TIÊN (KÈM TỌA ĐỘ)]:")
        for w in result.words[:5]:
            print(f"    - Từ: '{w.text:<15}' | Conf: {w.confidence:5.1f}% | Box: {w.bbox}")
        if len(result.words) > 5:
            print(f"    ... và {len(result.words) - 5} từ khác.")
    print("=" * 70)

def run_demo():
    print("*" * 70)
    print("       CHƯƠNG TRÌNH DEMO OCR SERVICE ĐỘC LẬP (TESSERACT OCR)       ")
    print("*" * 70)
    
    # 0. Kiểm tra Health Check của OCR Service
    health = ocr_service.health_check()
    print("\n[BƯỚC 0] Kiểm tra trạng thái hệ thống OCR (Health Check):")
    print(f"  - Trạng thái  : {health['status']}")
    print(f"  - Sẵn sàng    : {health['available']}")
    print(f"  - Engine      : {health['engine']} v{health.get('version', 'N/A')}")
    print(f"  - Ngôn ngữ hỗ trợ: {', '.join(health.get('languages', []))}")
    print(f"  - Binary Path : {health.get('binary_path', 'N/A')}")
    
    if not health["available"]:
        print("\n[CẢNH BÁO] Tesseract Engine chưa sẵn sàng. Vui lòng cài đặt theo hướng dẫn.")
        return

    # Nếu người dùng truyền file ảnh từ dòng lệnh
    if len(sys.argv) > 1:
        custom_file = sys.argv[1]
        print(f"\n[DEMO TÙY CHỌN] Đang xử lý file ảnh do người dùng chỉ định: {custom_file}")
        options = OCROptions(lang="vie+eng", extract_words=True, preprocess=True)
        res = ocr_service.process(custom_file, options=options)
        print_result_card("Xử lý file người dùng", res)
        return

    # Demo 1: Ảnh Tiếng Anh có chi tiết tọa độ từ
    sample_en = create_sample_image("Invoice #INV-2026-999: Amount $1,500.00 Paid", "demo_sample_en.png")
    try:
        opt_en = OCROptions(lang="eng", extract_words=True, preprocess=True)
        res_en = ocr_service.process(sample_en, options=opt_en)
        print_result_card("Test 1: Ảnh Hóa đơn Tiếng Anh (kèm tọa độ từ)", res_en)
    finally:
        if os.path.exists(sample_en):
            os.remove(sample_en)

    # Demo 2: Ảnh Tiếng Việt có dấu phức tạp
    sample_vn = create_sample_image("Cộng hòa Xã hội Chủ nghĩa Việt Nam - Độc lập Tự do", "demo_sample_vn.png", width=850)
    try:
        opt_vn = OCROptions(lang="vie+eng", preprocess=True, binarize=True)
        res_vn = ocr_service.process(sample_vn, options=opt_vn)
        print_result_card("Test 2: Ảnh Tiếng Việt Có Dấu (kết hợp Binarization)", res_vn)
    finally:
        if os.path.exists(sample_vn):
            os.remove(sample_vn)

    # Demo 3: Edge Case - Ảnh trắng không chứa chữ
    blank_img_path = create_sample_image("", "demo_sample_blank.png", width=400, height=100)
    try:
        res_blank = ocr_service.process(blank_img_path)
        print_result_card("Test 3: Edge Case - Ảnh Trắng Không Có Ký Tự (Status EMPTY)", res_blank)
    finally:
        if os.path.exists(blank_img_path):
            os.remove(blank_img_path)

    # Demo 4: Edge Case - File không tồn tại
    res_not_found = ocr_service.process("tep_tin_khong_he_ton_tai_12345.png")
    print_result_card("Test 4: Edge Case - File Không Tồn Tại (Status FAILED, Graceful Handling)", res_not_found)

    print("\n" + "*" * 70)
    print("=> DEMO HOÀN TẤT THÀNH CÔNG! OCR SERVICE HOẠT ĐỘNG HOÀN TOÀN ĐỘC LẬP.")
    print("*" * 70)

if __name__ == "__main__":
    run_demo()
