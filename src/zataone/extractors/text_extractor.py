# zataone text extractor

"""
Production-grade TextExtractor for text assets.
Extracts keyword and pattern signals for compliance evaluation.
Pure extractor—no DB writes.
"""

from __future__ import annotations
import re
import uuid
from dataclasses import dataclass
from typing import Any

from zataone.extractors.base import BaseExtractor

HIGH_RISK_KEYWORDS = [
    "guaranteed",
    "instant",
    "100%",
    "cure",
    "permanent",
    "no risk",
    "risk-free",
    "scientifically proven",
    "clinically proven",
]

PERCENTAGE_PATTERN = re.compile(r"\d+%")
TIME_CLAIM_PATTERN = re.compile(r"\d+\s*(days?|hours?|minutes?)", re.IGNORECASE)


@dataclass
class Signal:
    """Signal emitted by TextExtractor. Conforms to pipeline Signal schema."""

    signal_id: str
    signal_type: str
    source_model: str
    confidence: float
    raw_data: dict[str, Any]
    bounding_box: None = None


class TextExtractor(BaseExtractor):
    """
    Text-based signal extractor for compliance-sensitive content.
    Detects keywords and patterns (percentages, time claims).
    """

    extractor_id = "text_extractor"
    version = "1.0"

    def extract(self, asset: Any) -> list[Signal]:
        """
        Extract signals from text asset.

        Args:
            asset: Object with asset_id, content (str), type (str).

        Returns:
            List of Signal objects. Empty if asset.type != "text".
        """
        asset_type = (
            asset.get("type") if isinstance(asset, dict) else getattr(asset, "type", None)
        )
        if asset_type != "text":
            return []

        content = (
            asset.get("content", "") if isinstance(asset, dict) else getattr(asset, "content", "")
        ) or ""
        if not isinstance(content, str):
            content = str(content)

        signals: list[Signal] = []

        # 1. Keyword signals
        content_lower = content.lower()
        for keyword in HIGH_RISK_KEYWORDS:
            if keyword in content_lower:
                signals.append(
                    Signal(
                        signal_id=str(uuid.uuid4()),
                        signal_type="keyword",
                        source_model=self.extractor_id,
                        confidence=1.0,
                        raw_data={
                            "type": "keyword",
                            "text": keyword,
                            "value": keyword,
                        },
                    )
                )

        # 2. Pattern signals: percentage claims
        for match in PERCENTAGE_PATTERN.finditer(content):
            value = match.group(0)
            signals.append(
                Signal(
                    signal_id=str(uuid.uuid4()),
                    signal_type="percentage_claim",
                    source_model=self.extractor_id,
                    confidence=1.0,
                    raw_data={
                        "type": "percentage_claim",
                        "text": value,
                        "value": value,
                    },
                )
            )

        # 3. Pattern signals: time claims
        for match in TIME_CLAIM_PATTERN.finditer(content):
            value = match.group(0)
            signals.append(
                Signal(
                    signal_id=str(uuid.uuid4()),
                    signal_type="time_claim",
                    source_model=self.extractor_id,
                    confidence=1.0,
                    raw_data={
                        "type": "time_claim",
                        "text": value,
                        "value": value,
                    },
                )
            )

        return signals
