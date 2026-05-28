# zataone OCR extractor

"""
OCR extractor for image assets.
Extracts text via pytesseract, then applies keyword/pattern detection.
Reuses logic from TextExtractor.
"""

from __future__ import annotations
import base64
import logging
import uuid
from io import BytesIO
from typing import Any

from zataone.extractors.base import BaseExtractor
from zataone.extractors.text_extractor import (
    HIGH_RISK_KEYWORDS,
    PERCENTAGE_PATTERN,
    TIME_CLAIM_PATTERN,
    Signal,
)

logger = logging.getLogger(__name__)


def _check_tesseract_available() -> bool:
    """Lazy check for pytesseract/Pillow to avoid import-time segfaults on some systems."""
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401

        return True
    except ImportError:
        return False


class OCRExtractor(BaseExtractor):
    """
    OCR extractor for image assets.
    Extracts text via pytesseract, then detects keywords and patterns.
    """

    extractor_id = "ocr_extractor"
    version = "1.0"

    def extract(self, asset: Any) -> list[Signal]:
        """
        Extract signals from image asset.

        Args:
            asset: Object with type, image_data (bytes) or content (base64 str).

        Returns:
            List of Signal objects. Empty if asset.type != "image" or OCR fails.
        """
        asset_type = (
            asset.get("type") if isinstance(asset, dict) else getattr(asset, "type", None)
        )
        if asset_type != "image":
            return []

        image_bytes = self._get_image_bytes(asset)
        if image_bytes is None:
            return []

        if not _check_tesseract_available():
            logger.warning("pytesseract/Pillow not available; OCR skipped")
            return []

        try:
            extracted_text = self._run_ocr(image_bytes)
        except Exception as e:
            logger.exception("OCR failed: %s", e)
            return []

        if not extracted_text or not extracted_text.strip():
            return []

        text_lower = extracted_text.lower().strip()
        signals: list[Signal] = []

        # 1. Keyword signals
        for keyword in HIGH_RISK_KEYWORDS:
            if keyword in text_lower:
                signals.append(
                    Signal(
                        signal_id=str(uuid.uuid4()),
                        signal_type="ocr_keyword",
                        source_model=self.extractor_id,
                        confidence=0.9,
                        raw_data={
                            "source": "ocr",
                            "text": extracted_text,
                            "matched_value": keyword,
                        },
                    )
                )

        # 2. Percentage pattern signals
        for match in PERCENTAGE_PATTERN.finditer(extracted_text):
            value = match.group(0)
            signals.append(
                Signal(
                    signal_id=str(uuid.uuid4()),
                    signal_type="ocr_percentage_claim",
                    source_model=self.extractor_id,
                    confidence=0.9,
                    raw_data={
                        "source": "ocr",
                        "text": extracted_text,
                        "matched_value": value,
                    },
                )
            )

        # 3. Time claim pattern signals
        for match in TIME_CLAIM_PATTERN.finditer(extracted_text):
            value = match.group(0)
            signals.append(
                Signal(
                    signal_id=str(uuid.uuid4()),
                    signal_type="ocr_time_claim",
                    source_model=self.extractor_id,
                    confidence=0.9,
                    raw_data={
                        "source": "ocr",
                        "text": extracted_text,
                        "matched_value": value,
                    },
                )
            )

        return signals

    def _get_image_bytes(self, asset: Any) -> bytes | None:
        """Get image bytes from asset.image_data or asset.content (base64)."""
        image_data = (
            asset.get("image_data") if isinstance(asset, dict) else getattr(asset, "image_data", None)
        )
        if image_data is not None:
            if isinstance(image_data, bytes):
                return image_data
            if isinstance(image_data, bytearray):
                return bytes(image_data)
            return None

        content = (
            asset.get("content") if isinstance(asset, dict) else getattr(asset, "content", None)
        )
        if content is None:
            return None

        if isinstance(content, bytes):
            return content

        if isinstance(content, str):
            try:
                return base64.b64decode(content)
            except Exception:
                return None

        return None

    def _run_ocr(self, image_bytes: bytes) -> str:
        """Run pytesseract OCR on image bytes. Returns extracted text."""
        import pytesseract
        from PIL import Image

        image = Image.open(BytesIO(image_bytes))
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        return pytesseract.image_to_string(image) or ""
