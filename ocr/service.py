import time
from pathlib import Path
from typing import Any, Dict, Optional, Union
from PIL import Image

from .config import OCRConfig, ocr_config
from .schema import OCROptions, OCRResult, OCRMetadata, OCRStatus
from .processor import ImageProcessor
from .engine import TesseractEngine

class OCRService:
    """
    Dịch vụ OCR độc lập (Independent OCR Service).
    
    Cung cấp giao diện trừu tượng duy nhất để xử lý nhận diện văn bản từ hình ảnh
    dành cho bất kỳ Consumer nào (Agent, Chatbot, MCP Server, Tool, RAG...).
    
    Đặc điểm kiến trúc:
    - Hoàn toàn độc lập, không gắn chặt vào Attendance hay RAG logic.
    - Nhận đầu vào đa dạng: file path, bytes stream, hoặc PIL.Image.
    - Chuẩn hóa đầu ra thành OCRResult với đầy đủ metadata, độ tự tin và trạng thái.
    - Không làm crash ứng dụng khi file hỏng/lỗi động cơ, luôn trả về status có cấu trúc.
    """

    def __init__(
        self, 
        config: Optional[OCRConfig] = None,
        processor: Optional[ImageProcessor] = None,
        engine: Optional[TesseractEngine] = None
    ):
        self.config = config or ocr_config
        self.processor = processor or ImageProcessor(self.config)
        self.engine = engine or TesseractEngine(self.config)

    def process(
        self, 
        image_input: Union[str, Path, bytes, Image.Image], 
        options: Optional[OCROptions] = None
    ) -> OCRResult:
        """
        Quy trình xử lý OCR hoàn chỉnh:
        Load/Validate -> Preprocess -> OCR Extraction -> Build Metadata -> Return OCRResult.
        
        Args:
            image_input: Đường dẫn tệp ảnh, Path, dữ liệu bytes hoặc đối tượng PIL.Image.
            options: Cấu hình tùy chọn cho lần chạy này (ngôn ngữ, tiền xử lý, psm, timeout...).
            
        Returns:
            OCRResult: Đối tượng chứa văn bản trích xuất, trạng thái, độ tự tin và metadata.
        """
        opts = options or OCROptions()
        start_time = time.perf_counter()
        
        source_name = "unknown"
        img_width = 0
        img_height = 0
        img_format = None
        was_preprocessed = False

        try:
            # 1. Nạp và kiểm tra tính hợp lệ của ảnh
            raw_image, source_name, img_format = self.processor.load_and_validate(image_input)
            img_width, img_height = raw_image.size

            # 2. Tiền xử lý ảnh nếu được yêu cầu
            if opts.preprocess:
                processed_image = self.processor.preprocess(raw_image, opts)
                was_preprocessed = True
            else:
                processed_image = raw_image

            # 3. Thực hiện bóc tách ký tự qua OCR Engine
            extracted_text, avg_confidence, word_boxes = self.engine.extract(
                image=processed_image,
                lang=opts.lang,
                psm=opts.psm,
                oem=opts.oem,
                extract_words=opts.extract_words,
                timeout=opts.timeout_seconds
            )

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            cleaned_text = extracted_text.strip()
            
            # 4. Xác định trạng thái kết quả
            status = OCRStatus.SUCCESS if cleaned_text else OCRStatus.EMPTY
            words_count = len(cleaned_text.split()) if cleaned_text else 0

            metadata = OCRMetadata(
                source=source_name,
                image_width=img_width,
                image_height=img_height,
                image_format=img_format,
                language=opts.lang,
                word_count=words_count,
                char_count=len(cleaned_text),
                confidence=avg_confidence,
                duration_ms=duration_ms,
                engine="tesseract",
                preprocessed=was_preprocessed
            )

            return OCRResult(
                text=cleaned_text,
                status=status,
                metadata=metadata,
                words=word_boxes,
                error_message=None
            )

        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            error_msg = str(e)
            
            # Trả về kết quả FAILED có cấu trúc, không làm đổ vỡ chương trình của caller
            return OCRResult(
                text="",
                status=OCRStatus.FAILED,
                metadata=OCRMetadata(
                    source=source_name,
                    image_width=img_width,
                    image_height=img_height,
                    image_format=img_format,
                    language=opts.lang,
                    word_count=0,
                    char_count=0,
                    confidence=0.0,
                    duration_ms=duration_ms,
                    engine="tesseract",
                    preprocessed=was_preprocessed
                ),
                words=[],
                error_message=error_msg
            )

    def extract_text(
        self, 
        image_input: Union[str, Path, bytes, Image.Image], 
        options: Optional[OCROptions] = None
    ) -> str:
        """
        Hàm tiện ích nhanh (Shorthand): Trực tiếp trả về chuỗi văn bản bóc tách được.
        Nếu gặp lỗi, sẽ ném ra ngoại lệ RuntimeError chứa thông điệp lỗi.
        """
        result = self.process(image_input, options)
        if result.status == OCRStatus.FAILED:
            raise RuntimeError(f"OCR thất bại: {result.error_message}")
        return result.text

    def health_check(self) -> Dict[str, Any]:
        """
        Kiểm tra trạng thái sẵn sàng của OCR Service và Engine nền tảng.
        """
        is_avail = self.engine.is_available()
        version = None
        languages = []
        
        if is_avail:
            try:
                version = self.engine.get_version()
                languages = self.engine.get_available_languages()
            except Exception:
                pass

        return {
            "status": "healthy" if is_avail else "unhealthy",
            "engine": "tesseract",
            "available": is_avail,
            "version": version,
            "languages": languages,
            "binary_path": self.config.get_tesseract_binary_path(),
            "default_language": self.config.DEFAULT_LANG
        }

# Instance singleton mặc định dùng chung cho toàn bộ ứng dụng
ocr_service = OCRService()
