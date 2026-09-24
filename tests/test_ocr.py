import io
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image, ImageDraw, ImageFont

# Add root folder to sys.path
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from ocr import (
    OCRService,
    ocr_service,
    OCROptions,
    OCRResult,
    OCRMetadata,
    OCRStatus,
    WordBox
)
from ocr.config import OCRConfig

@pytest.fixture(scope="module")
def sample_english_image(tmp_path_factory) -> str:
    """Tạo một file ảnh chứa văn bản tiếng Anh rõ nét."""
    temp_dir = tmp_path_factory.mktemp("ocr_test_data")
    img_path = str(temp_dir / "english_sample.png")
    
    img = Image.new("RGB", (700, 150), color="white")
    draw = ImageDraw.Draw(img)
    
    font_path = r"C:\Windows\Fonts\arial.ttf"
    try:
        font = ImageFont.truetype(font_path, 32) if os.path.exists(font_path) else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
        
    draw.text((30, 50), "Hello World Invoice 2026 Verification", fill="black", font=font)
    img.save(img_path)
    return img_path

@pytest.fixture(scope="module")
def sample_vietnamese_image(tmp_path_factory) -> str:
    """Tạo một file ảnh chứa văn bản tiếng Việt có dấu rõ nét."""
    temp_dir = tmp_path_factory.mktemp("ocr_test_data")
    img_path = str(temp_dir / "vietnamese_sample.png")
    
    img = Image.new("RGB", (800, 150), color="white")
    draw = ImageDraw.Draw(img)
    
    font_path = r"C:\Windows\Fonts\arial.ttf"
    try:
        font = ImageFont.truetype(font_path, 30) if os.path.exists(font_path) else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
        
    draw.text((30, 50), "Cộng hòa Xã hội Chủ nghĩa Việt Nam", fill="black", font=font)
    img.save(img_path)
    return img_path

@pytest.fixture(scope="module")
def blank_image(tmp_path_factory) -> str:
    """Tạo một file ảnh màu trắng hoàn toàn không có văn bản."""
    temp_dir = tmp_path_factory.mktemp("ocr_test_data")
    img_path = str(temp_dir / "blank_sample.png")
    img = Image.new("RGB", (400, 200), color="white")
    img.save(img_path)
    return img_path

@pytest.fixture(scope="module")
def corrupt_image_file(tmp_path_factory) -> str:
    """Tạo một file có đuôi .png nhưng nội dung là rác không phải ảnh."""
    temp_dir = tmp_path_factory.mktemp("ocr_test_data")
    img_path = str(temp_dir / "corrupted.png")
    with open(img_path, "wb") as f:
        f.write(b"NOT_A_VALID_IMAGE_DATA_CORRUPTED_STREAM_12345")
    return img_path


class TestOCRServiceCore:
    """Kiểm thử toàn diện các chức năng cốt lõi của OCR Service."""

    def test_ocr_clear_english_text(self, sample_english_image):
        """1. Kiểm tra ảnh có chữ tiếng Anh rõ nét -> trích xuất chính xác."""
        result = ocr_service.process(sample_english_image)
        
        assert isinstance(result, OCRResult)
        assert result.status == OCRStatus.SUCCESS
        assert result.is_success is True
        assert result.is_empty is False
        assert result.has_error is False
        assert result.error_message is None
        
        # Kiểm tra nội dung các từ khóa
        text_lower = result.text.lower()
        assert "hello" in text_lower
        assert "world" in text_lower
        assert "invoice" in text_lower
        assert "2026" in text_lower
        
        # Kiểm tra metadata
        assert result.metadata.word_count >= 4
        assert result.metadata.char_count > 10
        assert result.metadata.image_width == 700
        assert result.metadata.image_height == 150
        assert result.metadata.duration_ms > 0
        assert result.metadata.confidence is not None
        assert result.metadata.confidence > 50.0

    def test_ocr_vietnamese_text(self, sample_vietnamese_image):
        """2. Kiểm tra ảnh có chữ tiếng Việt có dấu -> trích xuất tốt với ngôn ngữ vie+eng."""
        options = OCROptions(lang="vie+eng")
        result = ocr_service.process(sample_vietnamese_image, options=options)
        
        assert result.status == OCRStatus.SUCCESS
        assert result.is_success is True
        text_lower = result.text.lower()
        # Tesseract vie nhận diện tốt các từ khóa tiếng Việt
        assert "việt" in text_lower or "viet" in text_lower or "nam" in text_lower
        assert result.metadata.language == "vie+eng"

    def test_ocr_blank_image_returns_empty(self, blank_image):
        """3. Kiểm tra ảnh không có text (ảnh trắng) -> status EMPTY, không crash."""
        result = ocr_service.process(blank_image)
        
        assert result.status == OCRStatus.EMPTY
        assert result.is_empty is True
        assert result.is_success is False
        assert result.has_error is False
        assert result.text == ""
        assert result.metadata.word_count == 0

    def test_ocr_file_not_found(self):
        """4. Kiểm tra file không tồn tại -> status FAILED, có error_message, không crash."""
        non_existent_file = "d:/path/to/definitely_not_existing_file_9999.png"
        result = ocr_service.process(non_existent_file)
        
        assert result.status == OCRStatus.FAILED
        assert result.has_error is True
        assert result.is_success is False
        assert result.error_message is not None
        assert "không tồn tại" in result.error_message.lower()

    def test_ocr_corrupt_file(self, corrupt_image_file):
        """5. Kiểm tra file hỏng dữ liệu -> status FAILED, có thông báo lỗi hợp lệ."""
        result = ocr_service.process(corrupt_image_file)
        
        assert result.status == OCRStatus.FAILED
        assert result.has_error is True
        assert result.error_message is not None
        assert "không thể đọc" in result.error_message.lower() or "hỏng" in result.error_message.lower()

    def test_ocr_unsupported_extension(self, tmp_path):
        """Kiểm tra file có định dạng không được hỗ trợ (.txt, .exe...)."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("Hello")
        
        result = ocr_service.process(str(txt_file))
        assert result.status == OCRStatus.FAILED
        assert "không được hỗ trợ" in result.error_message.lower()

    def test_ocr_engine_failure_handling(self, sample_english_image):
        """6. Kiểm tra trường hợp OCR Engine bị lỗi (exception nội bộ) -> trả về status FAILED có cấu trúc."""
        with patch.object(ocr_service.engine, "extract", side_effect=RuntimeError("Mô phỏng lỗi Tesseract timeout")):
            result = ocr_service.process(sample_english_image)
            
            assert result.status == OCRStatus.FAILED
            assert result.has_error is True
            assert "Mô phỏng lỗi Tesseract timeout" in result.error_message

    def test_ocr_schema_and_interface(self, sample_english_image):
        """7. Kiểm tra tính toàn vẹn của schema đầu ra (OCRResult, OCRMetadata, OCRStatus)."""
        result = ocr_service.process(sample_english_image)
        
        # Kiểm tra kiểu dữ liệu
        data = result.model_dump()
        assert "text" in data
        assert "status" in data
        assert "metadata" in data
        assert "words" in data
        assert "error_message" in data
        
        meta = data["metadata"]
        assert isinstance(meta["image_width"], int)
        assert isinstance(meta["image_height"], int)
        assert isinstance(meta["duration_ms"], float)
        assert isinstance(meta["word_count"], int)
        assert isinstance(meta["char_count"], int)
        assert isinstance(meta["engine"], str)
        assert isinstance(meta["preprocessed"], bool)

    def test_ocr_bytes_input(self, sample_english_image):
        """8. Kiểm tra nạp ảnh trực tiếp qua dữ liệu bytes (ví dụ từ API multipart-upload)."""
        with open(sample_english_image, "rb") as f:
            image_bytes = f.read()
            
        result = ocr_service.process(image_bytes)
        assert result.status == OCRStatus.SUCCESS
        assert "hello" in result.text.lower()
        assert result.metadata.source == "bytes_stream"

    def test_ocr_pil_image_input(self):
        """Kiểm tra nạp ảnh trực tiếp từ đối tượng PIL.Image."""
        img = Image.new("RGB", (400, 100), color="white")
        draw = ImageDraw.Draw(img)
        draw.text((20, 30), "PIL Direct Input Test", fill="black")
        
        result = ocr_service.process(img)
        assert result.metadata.source == "pil_image"
        assert result.metadata.image_width == 400
        assert result.metadata.image_height == 100

    def test_ocr_extract_text_shorthand(self, sample_english_image):
        """Kiểm tra hàm tiện ích extract_text() trả về chuỗi text trực tiếp."""
        text = ocr_service.extract_text(sample_english_image)
        assert isinstance(text, str)
        assert "hello" in text.lower()
        
        # Kiểm tra trường hợp file không tồn tại sẽ ném ngoại lệ RuntimeError
        with pytest.raises(RuntimeError, match="OCR thất bại"):
            ocr_service.extract_text("non_existent_file_xyz.png")

    def test_ocr_extract_words_detailed(self, sample_english_image):
        """Kiểm tra tùy chọn extract_words=True để trích xuất tọa độ khung bao từng từ."""
        options = OCROptions(extract_words=True)
        result = ocr_service.process(sample_english_image, options=options)
        
        assert result.status == OCRStatus.SUCCESS
        assert len(result.words) > 0
        first_word = result.words[0]
        assert isinstance(first_word, WordBox)
        assert len(first_word.text) > 0
        assert first_word.confidence >= 0
        assert len(first_word.bbox) == 4

    def test_ocr_preprocessing_options(self, sample_english_image):
        """Kiểm tra các tùy chọn tiền xử lý: binarize, contrast_factor."""
        options = OCROptions(preprocess=True, binarize=True, contrast_factor=1.8)
        result = ocr_service.process(sample_english_image, options=options)
        
        assert result.status == OCRStatus.SUCCESS
        assert result.metadata.preprocessed is True
        assert "hello" in result.text.lower()

    def test_ocr_health_check(self):
        """Kiểm tra hàm health_check() báo cáo trạng thái engine chính xác."""
        health = ocr_service.health_check()
        assert isinstance(health, dict)
        assert health["status"] == "healthy"
        assert health["available"] is True
        assert health["engine"] == "tesseract"
        assert "vie" in health["languages"]
        assert "eng" in health["languages"]
