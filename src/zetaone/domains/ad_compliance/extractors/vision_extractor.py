"""
Vision extractor - detects objects in images (Grounding DINO).

Inherits from zetaone.extractors.base.BaseExtractor.
"""

from typing import List, Dict, Any, Optional
import sys
import os
import uuid
from io import BytesIO
from datetime import datetime

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

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
    import torch
    from PIL import Image
    from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection
    GROUNDING_DINO_AVAILABLE = True
except ImportError:
    GROUNDING_DINO_AVAILABLE = False

_dino_model: Optional["AutoModelForZeroShotObjectDetection"] = None
_dino_processor: Optional["AutoProcessor"] = None


class VisionExtractor(BaseExtractor):
    """Grounding DINO vision extractor for object detection."""

    extractor_id = "ad_compliance_vision"
    version = "1.0.0"

    def __init__(self, object_queries: List[str] = None):
        self.model_name = "grounding_dino"
        self._model = None
        self._processor = None
        self._device = "cpu"
        self._object_queries = object_queries or [
            "weapon", "gun", "knife", "pill", "medicine", "syringe",
            "money", "cash", "banknote",
        ]

    def _load_model(self) -> None:
        if not GROUNDING_DINO_AVAILABLE:
            raise ImportError(
                "Grounding DINO requires transformers, torch, and pillow. "
                "Install deps and ensure the model is available locally."
            )
        global _dino_model, _dino_processor
        if _dino_model is None or _dino_processor is None:
            model_id = "IDEA-Research/grounding-dino-base"
            _dino_processor = AutoProcessor.from_pretrained(model_id)
            _dino_model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id)
            _dino_model.eval()
        self._model = _dino_model
        self._processor = _dino_processor

    def extract(self, asset: Any) -> List[Signal]:
        """Extract object detection signals from asset image data."""
        image_data = getattr(asset, "image_data", None)
        if image_data is None or not GROUNDING_DINO_AVAILABLE:
            return []
        self._load_model()
        image = Image.open(BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        text_labels = [[q.lower() for q in self._object_queries]]
        inputs = self._processor(images=image, text=text_labels, return_tensors="pt").to(self._device)
        with torch.no_grad():
            outputs = self._model(**inputs)
        results = self._processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=0.3,
            text_threshold=0.3,
            target_sizes=[image.size[::-1]],
        )
        if not results:
            return []
        boxes = results[0].get("boxes", [])
        scores = results[0].get("scores", [])
        labels = results[0].get("text_labels", results[0].get("labels", []))
        signals = []
        for box, score, label in zip(boxes, scores, labels):
            conf = float(score)
            if conf < 0.3:
                continue
            x0, y0, x1, y1 = [float(v) for v in box.tolist()]
            w = max(0.0, x1 - x0)
            h = max(0.0, y1 - y0)
            payload = {
                "type": "vision_object",
                "label": str(label).strip().lower(),
                "confidence": conf,
                "bbox": [x0, y0, w, h],
                "source": "image",
                "model": "grounding_dino",
            }
            bounding_box = {"x": x0, "y": y0, "width": w, "height": h}
            signal = Signal(
                signal_id=str(uuid.uuid4()),
                signal_type=SignalType.OBJECT,
                source_model=self.model_name,
                confidence=conf,
                raw_data=payload,
                bounding_box=bounding_box,
                detected_at=datetime.now(),
            )
            signals.append(signal)
        return signals
