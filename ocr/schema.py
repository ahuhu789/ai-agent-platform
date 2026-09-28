from enum import Enum
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

class OCRStatus(str, Enum):
    """
    Trạng thái thực thi của quá trình OCR.
    """
    SUCCESS = "success"
    EMPTY = "empty"
    FAILED = "failed"

class OCROptions(BaseModel):
    """
    Tùy chọn khi gọi xử lý OCR.
    Cho phép tùy biến linh hoạt cho từng nhu cầu của Agent hoặc MCP.
    """
    lang: str = Field(
        default="vie+eng",
        description="Mã ngôn ngữ nhận diện (ví dụ: 'vie+eng', 'eng', 'vie')."
    )
    preprocess: bool = Field(
        default=True,
        description="Có thực hiện tiền xử lý ảnh (chuyển xám, khử nhiễu, tăng tương phản) không."
    )
    binarize: bool = Field(
        default=False,
        description="Có áp dụng phân ngưỡng nhị phân (binarization / thresholding) không."
    )
    contrast_factor: float = Field(
        default=1.5,
        ge=0.5,
        le=3.0,
        description="Hệ số tăng tương phản (mặc định 1.5)."
    )
    psm: Optional[int] = Field(
        default=3,
        ge=0,
        le=13,
        description="Page Segmentation Mode của Tesseract (mặc định 3: Fully automatic page segmentation)."
    )
    oem: Optional[int] = Field(
        default=3,
        ge=0,
        le=3,
        description="OCR Engine Mode của Tesseract (mặc định 3: Default, based on what is available)."
    )
    extract_words: bool = Field(
        default=False,
        description="Có trích xuất chi tiết từng từ kèm tọa độ và độ tự tin không."
    )
    timeout_seconds: Optional[int] = Field(
        default=30,
        ge=1,
        le=300,
        description="Thời gian tối đa chờ OCR trước khi ngắt (giây)."
    )

class WordBox(BaseModel):
    """
    Thông tin chi tiết một từ được bóc tách từ ảnh.
    """
    text: str = Field(..., description="Từ nhận diện được")
    confidence: float = Field(..., description="Độ tự tin nhận diện (0 - 100%)")
    bbox: Tuple[int, int, int, int] = Field(
        ..., 
        description="Tọa độ khung bao (x, y, width, height)"
    )

class OCRMetadata(BaseModel):
    """
    Metadata chi tiết về ảnh và quá trình xử lý OCR.
    """
    source: Optional[str] = Field(None, description="Tên file nguồn hoặc mô tả nguồn ảnh")
    image_width: int = Field(..., description="Chiều rộng ảnh (pixels)")
    image_height: int = Field(..., description="Chiều cao ảnh (pixels)")
    image_format: Optional[str] = Field(None, description="Định dạng ảnh (PNG, JPEG, ...)")
    language: str = Field(..., description="Ngôn ngữ sử dụng để OCR")
    word_count: int = Field(default=0, description="Tổng số từ nhận diện được")
    char_count: int = Field(default=0, description="Tổng số ký tự nhận diện được")
    confidence: Optional[float] = Field(
        None, 
        description="Độ tự tin trung bình (0.0 - 100.0%) của toàn bộ văn bản nhận diện"
    )
    duration_ms: float = Field(..., description="Thời gian thực thi OCR tính bằng mili-giây")
    engine: str = Field(default="tesseract", description="Tên engine OCR đã dùng")
    preprocessed: bool = Field(default=False, description="Ảnh có qua tiền xử lý không")

class OCRResult(BaseModel):
    """
    Kết quả trả về chuẩn hóa của OCR Service.
    Các module khác (Agents, Chatbot, MCP, RAG) chỉ cần tương tác qua model này.
    """
    text: str = Field(default="", description="Toàn bộ văn bản trích xuất được")
    status: OCRStatus = Field(..., description="Trạng thái kết quả: success, empty, failed")
    metadata: OCRMetadata = Field(..., description="Metadata quá trình OCR")
    words: List[WordBox] = Field(
        default_factory=list, 
        description="Danh sách các từ chi tiết (nếu bật extract_words)"
    )
    error_message: Optional[str] = Field(
        None, 
        description="Thông báo lỗi chi tiết nếu status == FAILED"
    )

    @property
    def is_success(self) -> bool:
        """Kiểm tra xử lý thành công và có nội dung."""
        return self.status == OCRStatus.SUCCESS and len(self.text.strip()) > 0

    @property
    def is_empty(self) -> bool:
        """Kiểm tra ảnh không chứa chữ hoặc không nhận diện được chữ nào."""
        return self.status == OCRStatus.EMPTY or len(self.text.strip()) == 0

    @property
    def has_error(self) -> bool:
        """Kiểm tra có phát sinh lỗi trong quá trình OCR không."""
        return self.status == OCRStatus.FAILED
