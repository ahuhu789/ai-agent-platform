"""Router xử lý nhận dạng ký tự quang học (OCR) cho Chatbot Web App."""

import logging
from typing import Optional
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from ocr import ocr_service, OCROptions, OCRStatus

logger = logging.getLogger("fme.api.ocr")

router = APIRouter(prefix="/ocr", tags=["OCR"])


@router.post(
    "/process",
    summary="Tải lên tệp ảnh hoặc PDF và thực hiện nhận dạng văn bản (OCR)",
    description=(
        "Nhận file ảnh (PNG, JPG, JPEG, WEBP, BMP, TIFF) hoặc tài liệu PDF tải lên, "
        "thực hiện tiền xử lý và gọi OCR / PyMuPDF để bóc tách văn bản tiếng Việt và tiếng Anh."
    ),
)
async def process_ocr_file(
    file: UploadFile = File(..., description="Tệp hình ảnh hoặc PDF cần OCR"),
    lang: str = Form("vie+eng", description="Gói ngôn ngữ OCR (vie+eng, vie, eng)"),
    preprocess: bool = Form(True, description="Bật tự động tiền xử lý ảnh (khử nhiễu, tăng nét)"),
    psm: int = Form(3, description="Page Segmentation Mode của Tesseract"),
):
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Tệp tải lên rỗng (0 bytes).")

        filename = file.filename or "uploaded_image.png"
        options = OCROptions(
            lang=lang,
            preprocess=preprocess,
            psm=psm,
        )

        # Gọi OCR Service độc lập
        result = ocr_service.process(content, options=options)

        # Gán tên file gốc vào metadata
        metadata_dict = result.metadata.model_dump()
        metadata_dict["source"] = filename

        return JSONResponse(
            content={
                "success": result.is_success,
                "status": result.status.value,
                "text": result.text,
                "metadata": metadata_dict,
                "error_message": result.error_message,
            }
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[OCR API] Lỗi trong quá trình xử lý: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "status": OCRStatus.FAILED.value,
                "text": "",
                "metadata": {
                    "source": getattr(file, "filename", "unknown"),
                    "duration_ms": 0,
                    "engine": "tesseract",
                },
                "error_message": f"Lỗi xử lý OCR: {str(exc)}",
            },
        )


@router.get(
    "/health",
    summary="Kiểm tra trạng thái sẵn sàng của OCR Engine",
)
def get_ocr_health():
    try:
        return ocr_service.health_check()
    except Exception as exc:
        return {
            "status": "error",
            "engine": "tesseract",
            "available": False,
            "error": str(exc),
        }
