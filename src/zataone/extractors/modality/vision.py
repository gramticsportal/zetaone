"""
Domain-agnostic Grounding DINO object detection. Model cache keyed by model_id.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

try:
    import torch
    from PIL import Image
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    GROUNDING_DINO_AVAILABLE = True
except ImportError:
    GROUNDING_DINO_AVAILABLE = False
    torch = None  # type: ignore

logger = logging.getLogger(__name__)

_model_cache: dict[str, tuple[Any, Any]] = {}


def _get_grounding_dino(model_id: str) -> tuple[Any, Any] | None:
    """Load (processor, model) once per model_id."""
    if not GROUNDING_DINO_AVAILABLE:
        return None
    if model_id in _model_cache:
        return _model_cache[model_id]
    try:
        processor = AutoProcessor.from_pretrained(model_id)
        model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id)
        model.eval()
    except Exception:
        logger.exception("modality.vision: Grounding DINO load failed for %s", model_id)
        return None
    _model_cache[model_id] = (processor, model)
    return _model_cache[model_id]


def detect_grounding_dino(
    image_data: bytes,
    *,
    object_queries: list[str],
    model_id: str = "IDEA-Research/grounding-dino-base",
    device: str = "cpu",
    detection_threshold: float = 0.3,
    text_threshold: float = 0.3,
    box_score_min: float = 0.3,
) -> list[dict[str, Any]]:
    """
    Run Grounding DINO and return raw detections (no domain Signal types).

    Each item: label (str), confidence (float), bbox [x0, y0, width, height].
    """
    if not GROUNDING_DINO_AVAILABLE or not image_data:
        return []
    loaded = _get_grounding_dino(model_id)
    if loaded is None:
        return []
    processor, model = loaded
    try:
        image = Image.open(BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        text_labels = [[q.lower() for q in object_queries]]
        inputs = processor(images=image, text=text_labels, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
        results = processor.post_process_grounded_object_detection(
            outputs,
            inputs.input_ids,
            threshold=detection_threshold,
            text_threshold=text_threshold,
            target_sizes=[image.size[::-1]],
        )
    except Exception:
        logger.exception("modality.vision: inference failed")
        return []
    if not results:
        return []
    boxes = results[0].get("boxes", [])
    scores = results[0].get("scores", [])
    labels = results[0].get("text_labels", results[0].get("labels", []))
    out: list[dict[str, Any]] = []
    for box, score, label in zip(boxes, scores, labels):
        conf = float(score)
        if conf < box_score_min:
            continue
        x0, y0, x1, y1 = [float(v) for v in box.tolist()]
        w = max(0.0, x1 - x0)
        h = max(0.0, y1 - y0)
        out.append(
            {
                "label": str(label).strip().lower(),
                "confidence": conf,
                "bbox": [x0, y0, w, h],
            }
        )
    return out
