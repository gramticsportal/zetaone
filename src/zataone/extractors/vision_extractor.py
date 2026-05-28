# zataone vision extractor

"""
Vision extractor for image assets.
Phase 2 MVP stub: dependency-free heuristic detection.
No ML models; safe fallback for visual compliance signals.
"""

from __future__ import annotations
import base64
import logging
import uuid
from typing import Any

from zataone.extractors.base import BaseExtractor
from zataone.extractors.text_extractor import Signal

logger = logging.getLogger(__name__)


class VisionExtractor(BaseExtractor):
    """
    Vision extractor for image assets.
    MVP stub: emits generic visual indicators without ML dependencies.
    """

    extractor_id = "vision_extractor"
    version = "1.0"

    def extract(self, asset: Any) -> list[Signal]:
        """
        Extract visual signals from image asset.

        Args:
            asset: Object with type, image_data (bytes) or content (base64 str).

        Returns:
            List of Signal objects. Empty if asset.type != "image" or no image data.
        """
        try:
            asset_type = (
                asset.get("type") if isinstance(asset, dict) else getattr(asset, "type", None)
            )
            if asset_type != "image":
                return []

            image_bytes = self._get_image_bytes(asset)
            if image_bytes is None:
                return []

            signals: list[Signal] = []

            # Generic: image exists
            signals.append(
                Signal(
                    signal_id=str(uuid.uuid4()),
                    signal_type="visual_indicator",
                    source_model=self.extractor_id,
                    confidence=0.5,
                    raw_data={
                        "source": "vision_stub",
                        "description": "image_present",
                        "value": "image_present",
                    },
                )
            )

            # Optional: visual content detected (size > 0)
            if len(image_bytes) > 0:
                signals.append(
                    Signal(
                        signal_id=str(uuid.uuid4()),
                        signal_type="visual_indicator",
                        source_model=self.extractor_id,
                        confidence=0.5,
                        raw_data={
                            "source": "vision_stub",
                            "description": "visual_content_detected",
                            "value": "visual_content_detected",
                        },
                    )
                )

            logger.info("VisionExtractor produced %d signals", len(signals))
            return signals

        except Exception as e:
            logger.exception("VisionExtractor failed: %s", e)
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
