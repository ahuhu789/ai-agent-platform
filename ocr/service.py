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

    @staticmethod
    def _is_pdf_input(image_input: Union[str, Path, bytes, Image.Image]) -> bool:
        """Kiểm tra xem đầu vào có phải là tệp hoặc luồng dữ liệu PDF hay không."""
        if isinstance(image_input, (str, Path)):
            return str(image_input).lower().endswith(".pdf")
        if isinstance(image_input, bytes):
            return image_input[:5].startswith(b"%PDF") or b"%PDF-" in image_input[:1024]
        return False

    def _process_pdf(
        self,
        pdf_input: Union[str, Path, bytes],
        opts: OCROptions,
        start_time: float
    ) -> OCRResult:
        """
        Quy trình xử lý OCR cho tài liệu PDF (hỗ trợ cả văn bản số & tài liệu scan/ảnh).
        """
        import io
        source_name = "document.pdf"
        page_texts = []
        confidences = []
        total_pages = 0
        img_width = 0
        img_height = 0
        was_preprocessed = False

        try:
            try:
                import pymupdf
                doc = None
                if isinstance(pdf_input, (str, Path)):
                    path_obj = Path(pdf_input)
                    source_name = path_obj.name
                    if not path_obj.exists():
                        raise FileNotFoundError(f"Tệp PDF không tồn tại: '{pdf_input}'")
                    doc = pymupdf.open(str(path_obj))
                elif isinstance(pdf_input, bytes):
                    source_name = "pdf_bytes"
                    if len(pdf_input) == 0:
                        raise ValueError("Dữ liệu PDF bytes rỗng (0 bytes).")
                    doc = pymupdf.open(stream=pdf_input, filetype="pdf")
                else:
                    raise TypeError(f"Kiểu dữ liệu PDF không hợp lệ: {type(pdf_input)}")

                total_pages = len(doc)
                if total_pages == 0:
                    raise ValueError("Tệp PDF không có trang nào.")

                for idx, page in enumerate(doc):
                    direct_text = page.get_text().strip()
                    # Nếu trang có sẵn văn bản số rõ ràng (>30 ký tự hoặc nhiều hơn 5 từ)
                    if len(direct_text) > 30 or len(direct_text.split()) > 5:
                        page_texts.append(direct_text)
                        confidences.append(100.0)
                        rect = page.rect
                        if rect.width > img_width:
                            img_width = int(rect.width)
                            img_height = int(rect.height)
                    else:
                        # Trang scan hoặc chứa ảnh: render trang sang ảnh và chạy Tesseract OCR
                        pix = page.get_pixmap(dpi=150)
                        img_width = max(img_width, pix.width)
                        img_height = max(img_height, pix.height)
                        page_img = Image.open(io.BytesIO(pix.tobytes("png")))

                        if opts.preprocess:
                            page_img = self.processor.preprocess(page_img, opts)
                            was_preprocessed = True

                        extracted_text, conf, _ = self.engine.extract(
                            image=page_img,
                            lang=opts.lang,
                            psm=opts.psm,
                            oem=opts.oem,
                            timeout=opts.timeout_seconds
                        )
                        cleaned = extracted_text.strip()
                        if cleaned:
                            page_texts.append(cleaned)
                        elif direct_text:
                            page_texts.append(direct_text)

                        if conf > 0:
                            confidences.append(conf)

            except ImportError:
                import pypdf
                if isinstance(pdf_input, (str, Path)):
                    path_obj = Path(pdf_input)
                    source_name = path_obj.name
                    reader = pypdf.PdfReader(str(path_obj))
                else:
                    reader = pypdf.PdfReader(io.BytesIO(pdf_input))

                total_pages = len(reader.pages)
                for idx, page in enumerate(reader.pages):
                    t = (page.extract_text() or "").strip()
                    if t:
                        page_texts.append(t)
                        confidences.append(100.0)

            # Tổng hợp văn bản theo từng trang nếu có nhiều hơn 1 trang
            if len(page_texts) == 1:
                combined_text = page_texts[0]
            elif len(page_texts) > 1:
                combined_text = "\n\n".join(
                    f"--- Trang {i + 1} ---\n{text}" for i, text in enumerate(page_texts)
                )
            else:
                combined_text = ""

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            cleaned_text = combined_text.strip()
            status = OCRStatus.SUCCESS if cleaned_text else OCRStatus.EMPTY
            avg_conf = round(sum(confidences) / len(confidences), 2) if confidences else 100.0
            words_count = len(cleaned_text.split()) if cleaned_text else 0

            metadata = OCRMetadata(
                source=source_name,
                image_width=img_width,
                image_height=img_height,
                image_format="PDF",
                language=opts.lang,
                word_count=words_count,
                char_count=len(cleaned_text),
                confidence=avg_conf,
                duration_ms=duration_ms,
                engine="tesseract+pymupdf",
                preprocessed=was_preprocessed
            )

            return OCRResult(
                text=cleaned_text,
                status=status,
                metadata=metadata,
                words=[],
                error_message=None
            )

        except Exception as e:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return OCRResult(
                text="",
                status=OCRStatus.FAILED,
                metadata=OCRMetadata(
                    source=source_name,
                    image_width=0,
                    image_height=0,
                    image_format="PDF",
                    language=opts.lang,
                    word_count=0,
                    char_count=0,
                    confidence=0.0,
                    duration_ms=duration_ms,
                    engine="tesseract+pymupdf",
                    preprocessed=False
                ),
                words=[],
                error_message=str(e)
            )

    def process(
        self, 
        image_input: Union[str, Path, bytes, Image.Image], 
        options: Optional[OCROptions] = None
    ) -> OCRResult:
        """
        Quy trình xử lý OCR hoàn chỉnh:
        Load/Validate -> Preprocess -> OCR Extraction -> Build Metadata -> Return OCRResult.
        Hỗ trợ hình ảnh (PNG, JPG, WEBP, BMP, TIFF) và tài liệu PDF.
        
        Args:
            image_input: Đường dẫn tệp ảnh/PDF, Path, dữ liệu bytes hoặc đối tượng PIL.Image.
            options: Cấu hình tùy chọn cho lần chạy này (ngôn ngữ, tiền xử lý, psm, timeout...).
            
        Returns:
            OCRResult: Đối tượng chứa văn bản trích xuất, trạng thái, độ tự tin và metadata.
        """
        opts = options or OCROptions()
        start_time = time.perf_counter()
        
        # Nếu đầu vào là tệp hoặc luồng dữ liệu PDF, điều hướng tới xử lý PDF chuyên dụng
        if self._is_pdf_input(image_input):
            return self._process_pdf(image_input, opts, start_time)
        
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
