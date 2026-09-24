import io
import os
from pathlib import Path
from typing import Tuple, Union, Optional
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
import numpy as np

from .config import OCRConfig, ocr_config
from .schema import OCROptions

class ImageProcessor:
    """
    Bộ tiền xử lý hình ảnh độc lập cho OCR.
    Thực hiện kiểm tra định dạng, xoay chuẩn hướng EXIF, tăng tương phản,
    chuyển xám và nhị phân hóa nhằm nâng cao chất lượng nhận diện của Tesseract.
    """

    def __init__(self, config: Optional[OCRConfig] = None):
        self.config = config or ocr_config

    def load_and_validate(
        self, 
        image_input: Union[str, Path, bytes, Image.Image]
    ) -> Tuple[Image.Image, Optional[str], Optional[str]]:
        """
        Nạp và kiểm tra tính hợp lệ của ảnh đầu vào.
        Hỗ trợ: đường dẫn file (str, Path), luồng nhị phân (bytes), hoặc đối tượng PIL.Image.
        
        Returns:
            Tuple[Image.Image, Optional[source_name], Optional[format]]
        """
        source_name: Optional[str] = None
        img_format: Optional[str] = None

        if isinstance(image_input, (str, Path)):
            path_obj = Path(image_input)
            source_name = path_obj.name

            # 1. Kiểm tra file tồn tại
            if not path_obj.exists():
                raise FileNotFoundError(f"Tệp hình ảnh không tồn tại: '{image_input}'")
            if not path_obj.is_file():
                raise ValueError(f"Đường dẫn chỉ định không phải là một tệp: '{image_input}'")

            # 2. Kiểm tra phần mở rộng
            ext = path_obj.suffix.lower()
            if ext not in self.config.ALLOWED_EXTENSIONS:
                raise ValueError(
                    f"Định dạng tệp '{ext}' không được hỗ trợ. "
                    f"Các định dạng hợp lệ: {', '.join(self.config.ALLOWED_EXTENSIONS)}"
                )

            # 3. Kiểm tra dung lượng
            size_mb = path_obj.stat().st_size / (1024 * 1024)
            if size_mb > self.config.MAX_IMAGE_SIZE_MB:
                raise ValueError(
                    f"Dung lượng tệp ({size_mb:.2f} MB) vượt quá giới hạn tối đa "
                    f"cho phép ({self.config.MAX_IMAGE_SIZE_MB} MB)."
                )

            try:
                img = Image.open(str(path_obj))
                img_format = img.format or ext.replace(".", "").upper()
                img.load()  # Xác thực dữ liệu ảnh không bị corrupt
            except Exception as e:
                raise ValueError(f"Không thể đọc file ảnh '{path_obj.name}'. File có thể bị hỏng: {e}")

        elif isinstance(image_input, bytes):
            source_name = "bytes_stream"
            if len(image_input) == 0:
                raise ValueError("Dữ liệu ảnh bytes rỗng (0 bytes).")
            
            size_mb = len(image_input) / (1024 * 1024)
            if size_mb > self.config.MAX_IMAGE_SIZE_MB:
                raise ValueError(
                    f"Dung lượng dữ liệu ảnh ({size_mb:.2f} MB) vượt quá giới hạn "
                    f"cho phép ({self.config.MAX_IMAGE_SIZE_MB} MB)."
                )

            try:
                stream = io.BytesIO(image_input)
                img = Image.open(stream)
                img_format = img.format
                img.load()
            except Exception as e:
                raise ValueError(f"Dữ liệu bytes không phải là định dạng hình ảnh hợp lệ: {e}")

        elif isinstance(image_input, Image.Image):
            source_name = "pil_image"
            img = image_input.copy()
            img_format = img.format or "RAW"
        else:
            raise TypeError(
                f"Kiểu dữ liệu đầu vào không hợp lệ: {type(image_input)}. "
                "Hỗ trợ: str (đường dẫn), Path, bytes hoặc PIL.Image."
            )

        # Chuẩn hóa hướng xoay dựa trên EXIF orientation nếu có
        try:
            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        return img, source_name, img_format

    def preprocess(
        self, 
        image: Image.Image, 
        options: OCROptions
    ) -> Image.Image:
        """
        Thực hiện tiền xử lý ảnh để cải thiện độ nét văn bản trước khi OCR:
        - Tự động upscale nếu ảnh quá nhỏ (chiều cao < 300px)
        - Chuyển sang ảnh thang độ xám (Grayscale)
        - Tăng tương phản (Contrast Enhancement)
        - Phân ngưỡng nhị phân (Binarization) nếu được yêu cầu
        """
        if not options.preprocess:
            return image

        processed = image.copy()

        # 1. Phóng to ảnh nhỏ để ký tự rõ hơn (DPI thấp -> DPI cao)
        w, h = processed.size
        if h < 300 or w < 300:
            scale_factor = max(300 / max(h, 1), 300 / max(w, 1))
            new_w = int(w * scale_factor)
            new_h = int(h * scale_factor)
            processed = processed.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # 2. Chuyển sang Grayscale (ảnh mức xám)
        if processed.mode != "L":
            processed = processed.convert("L")

        # 3. Tăng độ tương phản
        if options.contrast_factor and options.contrast_factor != 1.0:
            enhancer = ImageEnhance.Contrast(processed)
            processed = enhancer.enhance(options.contrast_factor)

        # 4. Phân ngưỡng nhị phân (Binarization / Otsu thresholding)
        if options.binarize:
            processed = self._apply_otsu_threshold(processed)

        return processed

    def _apply_otsu_threshold(self, gray_image: Image.Image) -> Image.Image:
        """
        Thuật toán Otsu tự động tìm ngưỡng phân tách sáng/tối tối ưu
        để biến ảnh xám thành ảnh đen trắng tuyệt đối (Black & White).
        """
        np_img = np.array(gray_image)
        hist, _ = np.histogram(np_img.ravel(), 256, [0, 256])
        total = np_img.size
        
        current_max, threshold = 0.0, 128
        sum_total = np.dot(np.arange(256), hist)
        sum_b, weight_b = 0.0, 0
        
        for t in range(256):
            weight_b += hist[t]
            if weight_b == 0:
                continue
            weight_f = total - weight_b
            if weight_f == 0:
                break
                
            sum_b += t * hist[t]
            mean_b = sum_b / weight_b
            mean_f = (sum_total - sum_b) / weight_f
            
            between_variance = weight_b * weight_f * ((mean_b - mean_f) ** 2)
            if between_variance > current_max:
                current_max = between_variance
                threshold = t
                
        # Áp dụng ngưỡng
        binary_arr = (np_img > threshold) * 255
        return Image.fromarray(binary_arr.astype(np.uint8), mode="L")
