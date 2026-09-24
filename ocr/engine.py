import os
from typing import Dict, List, Optional, Tuple
from PIL import Image

from .config import OCRConfig, ocr_config
from .schema import WordBox

class TesseractEngine:
    """
    Lớp giao tiếp trực tiếp với Tesseract OCR Engine thông qua thư viện pytesseract.
    Quản lý việc định vị binary, cấu hình tham số thực thi, và trích xuất dữ liệu.
    """

    def __init__(self, config: Optional[OCRConfig] = None):
        self.config = config or ocr_config
        self._binary_path: Optional[str] = None
        self._setup_tesseract_binary()

    def _setup_tesseract_binary(self) -> None:
        """
        Tìm kiếm và thiết lập đường dẫn thực thi cho pytesseract.
        """
        try:
            import pytesseract
            binary = self.config.get_tesseract_binary_path()
            if binary:
                pytesseract.pytesseract.tesseract_cmd = binary
                self._binary_path = binary
            else:
                self._binary_path = None
        except ImportError:
            self._binary_path = None

    def is_available(self) -> bool:
        """
        Kiểm tra xem Tesseract binary có sẵn sàng thực thi trên hệ thống không.
        """
        if not self._binary_path or not os.path.exists(self._binary_path):
            self._setup_tesseract_binary()
        return bool(self._binary_path and os.path.exists(self._binary_path))

    def get_version(self) -> str:
        """Lấy phiên bản hiện tại của Tesseract OCR."""
        self._ensure_available()
        import pytesseract
        return str(pytesseract.get_tesseract_version())

    def get_available_languages(self) -> List[str]:
        """Lấy danh sách các gói ngôn ngữ đã được cài đặt trong tessdata."""
        self._ensure_available()
        import pytesseract
        try:
            return pytesseract.get_languages()
        except Exception:
            return []

    def _ensure_available(self) -> None:
        """Ném lỗi có hướng dẫn cụ thể nếu Tesseract chưa được cài đặt/cấu hình."""
        if not self.is_available():
            raise RuntimeError(
                "Không tìm thấy công cụ Tesseract OCR trên hệ thống!\n"
                "Vui lòng cài đặt Tesseract OCR và cấu hình đường dẫn tại biến môi trường "
                "TESSERACT_PATH hoặc đảm bảo có tệp thực thi tại: 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'.\n"
                "Tải bộ cài đặt Windows tại: https://github.com/UB-Mannheim/tesseract/wiki"
            )

    def extract(
        self, 
        image: Image.Image, 
        lang: str, 
        psm: Optional[int] = 3, 
        oem: Optional[int] = 3, 
        extract_words: bool = False,
        timeout: Optional[int] = None
    ) -> Tuple[str, Optional[float], List[WordBox]]:
        """
        Thực hiện OCR trên đối tượng hình ảnh.
        
        Returns:
            Tuple[text, average_confidence, list_of_word_boxes]
        """
        self._ensure_available()
        import pytesseract

        # Xây dựng chuỗi tham số bổ sung cho Tesseract
        custom_config_parts = []
        if psm is not None:
            custom_config_parts.append(f"--psm {psm}")
        if oem is not None:
            custom_config_parts.append(f"--oem {oem}")
        custom_config = " ".join(custom_config_parts)

        timeout_sec = timeout or self.config.TIMEOUT_SECONDS

        # 1. Trích xuất text thông thường
        text = pytesseract.image_to_string(
            image, 
            lang=lang, 
            config=custom_config, 
            timeout=timeout_sec
        )

        avg_confidence: Optional[float] = None
        word_boxes: List[WordBox] = []

        # 2. Thu thập dữ liệu chi tiết (độ tự tin và tọa độ từ) qua image_to_data
        try:
            data = pytesseract.image_to_data(
                image, 
                lang=lang, 
                config=custom_config, 
                timeout=timeout_sec,
                output_type=pytesseract.Output.DICT
            )
            
            confs = []
            n_boxes = len(data["text"])
            for i in range(n_boxes):
                w_text = data["text"][i].strip()
                conf_val = float(data["conf"][i])
                
                # Chỉ lấy các khối từ thực tế (conf >= 0)
                if conf_val >= 0 and len(w_text) > 0:
                    confs.append(conf_val)
                    if extract_words:
                        word_boxes.append(WordBox(
                            text=w_text,
                            confidence=round(conf_val, 2),
                            bbox=(
                                data["left"][i],
                                data["top"][i],
                                data["width"][i],
                                data["height"][i]
                            )
                        ))

            if confs:
                avg_confidence = round(sum(confs) / len(confs), 2)
        except Exception:
            # Nếu image_to_data gặp lỗi thứ cấp, vẫn ưu tiên giữ text đã lấy được
            pass

        return text, avg_confidence, word_boxes
