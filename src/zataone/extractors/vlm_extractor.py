# zataone VLM extractor

"""
VLM (Vision-Language Model) extractor for contextual signal detection.
MVP stub: no external models; heuristic phrase and image detection.
"""

from __future__ import annotations
import base64
import logging
import uuid
from typing import Any

from zataone.extractors.base import BaseExtractor
from zataone.extractors.text_extractor import Signal

logger = logging.getLogger(__name__)

HIGH_RISK_CONTEXTUAL_PHRASES = [
    "clinically proven",
    "doctor recommended",
    "FDA approved",
    "scientifically proven",
    "medical breakthrough",
]


class VLMExtractor(BaseExtractor):
    """
    VLM extractor for text and image assets.
    MVP stub: detects high-risk contextual phrases (text) or emits generic signal (image).
    """

    extractor_id = "vlm_extractor"
    version = "1.0"

    def extract(self, asset: Any) -> list[Signal]:
        """
        Extract contextual signals from text or image asset.

        Args:
            asset: Object or dict with type, content (str) or image_data (bytes).

        Returns:
            List of Signal objects. Empty if no valid input.
        """
        try:
            asset_type = (
                asset.get("type") if isinstance(asset, dict) else getattr(asset, "type", None)
            )
            if asset_type not in ("text", "image"):
                return []

            signals: list[Signal] = []

            if asset_type == "text":
                content = (
                    asset.get("content", "")
                    if isinstance(asset, dict)
                    else getattr(asset, "content", "")
                )
                if content is None or (isinstance(content, str) and not content.strip()):
                    return []
                text = content if isinstance(content, str) else str(content)
                text_lower = text.lower()

                for phrase in HIGH_RISK_CONTEXTUAL_PHRASES:
                    if phrase.lower() in text_lower:
                        signals.append(
                            Signal(
                                signal_id=str(uuid.uuid4()),
                                signal_type="vlm_contextual_claim",
                                source_model=self.extractor_id,
                                confidence=0.6,
                                raw_data={
                                    "source": "vlm_stub",
                                    "matched_value": phrase,
                                    "modality": "text",
                                },
                            )
                        )

            elif asset_type == "image":
                image_bytes = self._get_image_bytes(asset)
                if image_bytes is not None and len(image_bytes) > 0:
                    signals.append(
                        Signal(
                            signal_id=str(uuid.uuid4()),
                            signal_type="vlm_contextual_claim",
                            source_model=self.extractor_id,
                            confidence=0.6,
                            raw_data={
                                "source": "vlm_stub",
                                "matched_value": "visual_content_detected",
                                "modality": "image",
                            },
                        )
                    )

            logger.info("VLMExtractor produced %d signals", len(signals))
            return signals

        except Exception as e:
            logger.exception("VLMExtractor failed: %s", e)
            return []

    def _get_image_bytes(self, asset: Any) -> bytes | None:
        """Get image bytes from asset.image_data or asset.content (base64)."""
        image_data = (
            asset.get("image_data")
            if isinstance(asset, dict)
            else getattr(asset, "image_data", None)
        )
        if image_data is not None:
            if isinstance(image_data, bytes):
                return image_data
            if isinstance(image_data, bytearray):
                return bytes(image_data)
            return None

        content = (
            asset.get("content")
            if isinstance(asset, dict)
            else getattr(asset, "content", None)
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
