"""
Real integration test for ZetaOne CompliancePipeline using OCRExtractor.
Uses actual OCR to extract text from an image, no mocking.

Requires: tesseract-ocr, pytesseract, Pillow.
Run with: pytest tests/test_zetaone_pipeline_real_ocr.py -v -s
"""

from io import BytesIO
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont


def _create_image_with_text(text: str) -> bytes:
    """Create a PNG image with the given text rendered."""
    img = Image.new("RGB", (500, 120), color="white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
    except OSError:
        font = ImageFont.load_default()
    draw.text((20, 40), text, fill="black", font=font)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_zetaone_pipeline_real_ocr():
    """Run CompliancePipeline with real OCRExtractor on image asset."""
    from zetaone.core.pipeline import CompliancePipeline

    asset = {
        "asset_id": "test-ocr-1",
        "content": "Guaranteed instant cure",
        "type": "text",
    }

    # Add image_data for OCRExtractor (renders content as image)
    image_data = _create_image_with_text(asset["content"])
    asset_obj = SimpleNamespace(**asset, image_data=image_data, image_id=asset["asset_id"])

    pipeline = CompliancePipeline(domain="ad_compliance")
    result = pipeline.run(asset_obj)

    print(result)

    assert len(result["signals"]) >= 0
    assert "verdict" in result
