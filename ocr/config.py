import os
import shutil
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv

# Tải các biến môi trường nếu có
load_dotenv()

class OCRConfig:
    """
    Cấu hình quản lý độc lập cho OCR Service.
    Không phụ thuộc vào bất kỳ Agent, RAG hay MCP nào.
    """
    # Ngôn ngữ nhận diện mặc định (vie + eng)
    DEFAULT_LANG: str = os.getenv("OCR_DEFAULT_LANG", "vie+eng")
    
    # Thời gian timeout thực thi OCR tính bằng giây
    TIMEOUT_SECONDS: int = int(os.getenv("OCR_TIMEOUT_SECONDS", "30"))
    
    # Dung lượng file ảnh tối đa cho phép (MB)
    MAX_IMAGE_SIZE_MB: int = int(os.getenv("OCR_MAX_IMAGE_SIZE_MB", "25"))
    
    # Các định dạng file ảnh được hỗ trợ
    ALLOWED_EXTENSIONS: tuple = (
        ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"
    )
    
    # Tự động tiền xử lý ảnh (chuyển xám, khử nhiễu, tăng tương phản)
    ENABLE_PREPROCESSING: bool = os.getenv("OCR_ENABLE_PREPROCESSING", "true").lower() == "true"
    
    # Đường dẫn cài đặt mặc định trên Windows nếu Tesseract không có trong PATH
    DEFAULT_WINDOWS_PATHS: List[str] = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expanduser(r"~\AppData\Local\Tesseract-OCR\tesseract.exe"),
    ]
    
    @classmethod
    def get_tesseract_binary_path(cls) -> Optional[str]:
        """
        Tìm kiếm đường dẫn thực thi của Tesseract binary:
        1. Từ biến môi trường TESSERACT_PATH hoặc TESSERACT_CMD
        2. Từ hệ thống PATH (shutil.which)
        3. Từ các đường dẫn chuẩn phổ biến trên Windows
        """
        # 1. Kiểm tra biến môi trường chỉ định rõ
        env_cmd = os.getenv("TESSERACT_PATH") or os.getenv("TESSERACT_CMD")
        if env_cmd and os.path.exists(env_cmd):
            return env_cmd
            
        # 2. Kiểm tra trong PATH hệ thống
        which_path = shutil.which("tesseract")
        if which_path and os.path.exists(which_path):
            return which_path
            
        # 3. Kiểm tra các thư mục mặc định trên Windows
        for win_path in cls.DEFAULT_WINDOWS_PATHS:
            if os.path.exists(win_path):
                return win_path
                
        return None

# Instance singleton cấu hình OCR
ocr_config = OCRConfig()
