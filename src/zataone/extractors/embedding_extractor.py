# zataone embedding extractor

"""
Embedding extractor for semantic signal detection.
MVP stub: uses semantic keyword groups as proxy for embeddings.
No external ML; deterministic keyword matching.
"""

from __future__ import annotations
import logging
import uuid
from typing import Any

from zataone.extractors.base import BaseExtractor
from zataone.extractors.text_extractor import Signal

logger = logging.getLogger(__name__)

MEDICAL_CLAIMS = [
    "heal",
    "treat",
    "diagnose",
    "prevent disease",
    "medical grade",
    "clinically proven",
]

GUARANTEE_CLAIMS = [
    "guaranteed results",
    "permanent results",
    "no side effects",
    "zero risk",
]


class EmbeddingExtractor(BaseExtractor):
    """
    Semantic signal extractor for text assets.
    MVP stub: detects semantic risk patterns via keyword clusters.
    """

    extractor_id = "embedding_extractor"
    version = "1.0"

    def extract(self, asset: Any) -> list[Signal]:
        """
        Extract semantic signals from text asset.

        Args:
            asset: Object with type, content (str).

        Returns:
            List of Signal objects. Empty if asset.type != "text" or content missing.
        """
        try:
            asset_type = (
                asset.get("type") if isinstance(asset, dict) else getattr(asset, "type", None)
            )
            if asset_type != "text":
                return []

            content = (
                asset.get("content", "")
                if isinstance(asset, dict)
                else getattr(asset, "content", "")
            )
            if content is None or (isinstance(content, str) and not content.strip()):
                return []

            text = content if isinstance(content, str) else str(content)
            text_lower = text.lower()

            signals: list[Signal] = []

            for phrase in MEDICAL_CLAIMS:
                if phrase in text_lower:
                    signals.append(
                        Signal(
                            signal_id=str(uuid.uuid4()),
                            signal_type="semantic_claim",
                            source_model=self.extractor_id,
                            confidence=0.7,
                            raw_data={
                                "source": "embedding_stub",
                                "matched_value": phrase,
                                "category": "medical_claim",
                            },
                        )
                    )

            for phrase in GUARANTEE_CLAIMS:
                if phrase in text_lower:
                    signals.append(
                        Signal(
                            signal_id=str(uuid.uuid4()),
                            signal_type="semantic_claim",
                            source_model=self.extractor_id,
                            confidence=0.7,
                            raw_data={
                                "source": "embedding_stub",
                                "matched_value": phrase,
                                "category": "guarantee_claim",
                            },
                        )
                    )

            logger.info("EmbeddingExtractor produced %d signals", len(signals))
            return signals

        except Exception as e:
            logger.exception("EmbeddingExtractor failed: %s", e)
            return []
