import os
import sys
from PIL import Image, ImageDraw, ImageFont

# Force UTF-8 output on Windows terminals
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Add root folder to sys.path
sys.path.insert(0, os.path.abspath("."))

from ocr import ocr_service, OCROptions

def generate_test_image(file_path: str, text: str):
    """Generate a clean sample image with text for OCR testing."""
    img = Image.new("RGB", (800, 150), color="white")
    canvas = ImageDraw.Draw(img)
    try:
        font_path = r"C:\Windows\Fonts\arial.ttf"
        font = ImageFont.truetype(font_path, 32) if os.path.exists(font_path) else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    canvas.text((40, 55), text, fill="black", font=font)
    img.save(file_path)
    print(f"[TEST SETUP] Created test image: {file_path}")

def run_ocr_test():
    print("=" * 60)
    print("RUNNING STANDALONE OCR TEST")
    print("=" * 60)
    os.makedirs("scratch", exist_ok=True)
    test_image_path = os.path.abspath("scratch/temp_ocr_test.png")
    test_text = "AI Agent Platform OCR Test - Hello World - 12345"
    generate_test_image(test_image_path, test_text)
    
    try:
        result = ocr_service.process(test_image_path, OCROptions(lang="eng", preprocess=True))
        print(f"Status: {result.status}")
        print(f"Text: '{result.text}'")
        print(f"Confidence: {result.metadata.confidence}%")
        assert "Hello World" in result.text or "12345" in result.text
        print(">> Standalone OCR test PASSED!")
    finally:
        if os.path.exists(test_image_path):
            try:
                os.remove(test_image_path)
            except Exception:
                pass

if __name__ == "__main__":
    run_ocr_test()
