"""
OCR Service Module
------------------
Module xử lý nhận dạng ký tự quang học (OCR) độc lập trong hệ thống.
Cung cấp dịch vụ trích xuất văn bản từ hình ảnh và tài liệu cho các Agent,
Chatbot, MCP Server hoặc RAG pipeline mà không gây ràng buộc kiến trúc.
"""

from .config import OCRConfig, ocr_config
from .schema import OCRResult, OCROptions, OCRMetadata, OCRStatus, WordBox
from .processor import ImageProcessor
from .engine import TesseractEngine
from .service import OCRService, ocr_service

__all__ = [
    "OCRConfig",
    "ocr_config",
    "OCRResult",
    "OCROptions",
    "OCRMetadata",
    "OCRStatus",
    "WordBox",
    "ImageProcessor",
    "TesseractEngine",
    "OCRService",
    "ocr_service",
]
