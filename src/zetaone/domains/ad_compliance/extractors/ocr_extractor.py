"""
OCR extractor - extracts text from images.

Uses a backend abstraction to support multiple OCR providers.
Inherits from zetaone.extractors.base.BaseExtractor.
"""

from typing import List, Dict, Any
from abc import ABC, abstractmethod
import sys
import os
from io import BytesIO
import uuid
from datetime import datetime

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# Add zetaone package path when running as part of ZetaOne (parent of zetaone pkg)
_zetaone_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_src_root = os.path.dirname(_zetaone_dir)
if os.path.exists(os.path.join(_zetaone_dir, "extractors", "base.py")):
    if _src_root not in sys.path:
        sys.path.insert(0, _src_root)

try:
    from zetaone.extractors.base import BaseExtractor
except ImportError:
    from abc import ABC, abstractmethod
    class BaseExtractor(ABC):
        extractor_id: str = ""
        version: str = ""
        @abstractmethod
        def extract(self, asset): pass
from schemas.models import Signal, SignalType

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


class OCRBackend(ABC):
    """Abstract base class for OCR backends."""

    @abstractmethod
    def extract_text_data(self, image_data: bytes) -> List[Dict[str, Any]]:
        """Extract text data from image."""
        pass


class TesseractOCRBackend(OCRBackend):
    """Tesseract OCR backend using pytesseract."""

    def __init__(self):
        if not TESSERACT_AVAILABLE:
            raise ImportError(
                "pytesseract and Pillow are required for TesseractOCRBackend. "
                "Install with: pip install pytesseract pillow"
            )
        self.backend_name = "tesseract"

    def extract_text_data(self, image_data: bytes) -> List[Dict[str, Any]]:
        image = Image.open(BytesIO(image_data))
        ocr_data = pytesseract.image_to_data(
            image,
            output_type=pytesseract.Output.DICT
        )
        results = []
        num_detections = len(ocr_data.get('text', []))
        for i in range(num_detections):
            text = ocr_data.get('text', [])[i]
            conf = ocr_data.get('conf', [])[i]
            left = ocr_data.get('left', [])[i]
            top = ocr_data.get('top', [])[i]
            width = ocr_data.get('width', [])[i]
            height = ocr_data.get('height', [])[i]
            if not text or not text.strip():
                continue
            if conf == -1 or conf < 40:
                continue
            normalized_confidence = conf / 100.0
            result = {
                "type": "ocr_text",
                "value": text.strip(),
                "confidence": normalized_confidence,
                "source": "image",
                "bbox": [int(left), int(top), int(width), int(height)]
            }
            results.append(result)
        return results


def get_ocr_backend(backend_type: str = "tesseract") -> OCRBackend:
    """Factory function to get OCR backend instance."""
    if backend_type == "tesseract":
        return TesseractOCRBackend()
    elif backend_type == "google_vision":
        raise ValueError("Google Vision backend not yet implemented")
    else:
        raise ValueError(f"Unsupported OCR backend type: {backend_type}")


class OCRExtractor(BaseExtractor):
    """OCR extractor that extracts text from images. Uses backend abstraction."""

    extractor_id = "ad_compliance_ocr"
    version = "1.0.0"

    def __init__(self, backend: OCRBackend = None):
        if backend is None:
            try:
                self.backend = get_ocr_backend("tesseract")
                self.model_name = "ocr_tesseract"
            except (ImportError, ValueError):
                self.backend = None
                self.model_name = "ocr_placeholder"
        else:
            self.backend = backend
            self.model_name = f"ocr_{backend.backend_name}"

    def extract(self, asset: Any) -> List[Signal]:
        """Extract text signals from asset image data."""
        image_data = getattr(asset, "image_data", None)
        if image_data is None or self.backend is None:
            return []
        ocr_results = self.backend.extract_text_data(image_data)
        signals = []
        for ocr_result in ocr_results:
            bbox_list = ocr_result.get("bbox", [0, 0, 0, 0])
            if len(bbox_list) == 4:
                bbox = {
                    "x": float(bbox_list[0]),
                    "y": float(bbox_list[1]),
                    "width": float(bbox_list[2]),
                    "height": float(bbox_list[3])
                }
            else:
                bbox = None
            signal = Signal(
                signal_id=str(uuid.uuid4()),
                signal_type=SignalType.TEXT,
                source_model=self.model_name,
                confidence=ocr_result.get("confidence", 0.0),
                raw_data={
                    "text": ocr_result.get("value", ""),
                    "type": ocr_result.get("type", "ocr_text"),
                    "source": ocr_result.get("source", "image"),
                    "bbox": bbox_list
                },
                bounding_box=bbox,
                detected_at=datetime.now()
            )
            signals.append(signal)
        return signals
