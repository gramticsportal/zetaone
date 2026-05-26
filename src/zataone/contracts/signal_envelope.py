"""
Canonical signal envelope for multimodal compliance (playbook-aligned).

Domain extractors may still use `schemas.models.Signal`; this type documents
the intended cross-domain shape and supports validation / serialization.

Usage:
    env = SignalEnvelope.from_extractor_signal(sig, modality="text")
    errors = env.validate()
    payload = env.to_dict()
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Modality = Literal["text", "image", "video", "audio"]
AnchorType = Literal["text_span", "image_bbox", "video_timerange", "audio_timerange", "none"]


# ── Per-modality anchor shapes ────────────────────────────────────────────────


@dataclass
class TextAnchor:
    """Character-offset anchor for text signals."""
    char_start: int
    char_end: int
    snippet: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"char_start": self.char_start, "char_end": self.char_end, "snippet": self.snippet}


@dataclass
class ImageAnchor:
    """Bounding-box anchor for image signals (relative 0-1 coords)."""
    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass
class TimeRangeAnchor:
    """Time-range anchor for video/audio signals."""
    start_seconds: float
    end_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {"start_seconds": self.start_seconds, "end_seconds": self.end_seconds}


# ── Canonical envelope ────────────────────────────────────────────────────────


@dataclass
class SignalEnvelope:
    """
    Logical signal shape shared across domains and modalities.

    Maps naturally to persisted ``signals.value`` JSON and API responses.
    """

    signal_id: str
    modality: Modality
    signal_type: str
    confidence: float
    extractor_id: str
    model_version: str
    value: dict[str, Any] = field(default_factory=dict)
    anchor: Optional[dict[str, Any]] = None
    anchor_type: AnchorType = "none"

    # ── Factories ──────────────────────────────────────────────────────────

    @classmethod
    def from_extractor_signal(
        cls,
        sig: Any,
        modality: Modality = "text",
    ) -> "SignalEnvelope":
        """
        Build a ``SignalEnvelope`` from any extractor ``Signal`` dataclass.

        Inspects ``raw_data`` for offset/text (text signals) and
        ``bounding_box`` (image signals) to populate the anchor.
        """
        rd: dict[str, Any] = getattr(sig, "raw_data", {}) or {}
        offset = rd.get("offset")
        text_snippet = rd.get("text", "")

        anchor: Optional[dict[str, Any]] = None
        anchor_type: AnchorType = "none"

        if modality == "text" and offset is not None and text_snippet:
            anchor = TextAnchor(
                char_start=int(offset),
                char_end=int(offset) + len(text_snippet),
                snippet=text_snippet,
            ).to_dict()
            anchor_type = "text_span"

        elif modality == "image":
            bb = getattr(sig, "bounding_box", None)
            if isinstance(bb, dict):
                anchor = bb
                anchor_type = "image_bbox"
            elif bb is not None:
                anchor = {"raw": str(bb)}
                anchor_type = "image_bbox"

        elif modality in ("video", "audio"):
            start = rd.get("start_seconds")
            end = rd.get("end_seconds")
            if start is not None and end is not None:
                anchor = TimeRangeAnchor(
                    start_seconds=float(start),
                    end_seconds=float(end),
                ).to_dict()
                anchor_type = "video_timerange" if modality == "video" else "audio_timerange"

        version = getattr(sig, "version", None) or getattr(
            type(sig), "version", "unknown"
        )

        return cls(
            signal_id=str(getattr(sig, "signal_id", uuid.uuid4())),
            modality=modality,
            signal_type=str(getattr(sig, "signal_type", "")),
            confidence=float(getattr(sig, "confidence", 0.5)),
            extractor_id=str(getattr(sig, "source_model", "")),
            model_version=str(version),
            value=rd,
            anchor=anchor,
            anchor_type=anchor_type,
        )

    # ── Validation ─────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """Return list of validation error strings (empty = valid)."""
        errors: list[str] = []
        if not self.signal_id:
            errors.append("signal_id is required")
        if not self.signal_type:
            errors.append("signal_type is required")
        if not self.extractor_id:
            errors.append("extractor_id is required")
        if not 0.0 <= self.confidence <= 1.0:
            errors.append(f"confidence must be in [0, 1], got {self.confidence}")
        if self.modality not in ("text", "image", "video", "audio"):
            errors.append(f"unknown modality: {self.modality!r}")
        if self.anchor_type not in (
            "text_span", "image_bbox", "video_timerange", "audio_timerange", "none"
        ):
            errors.append(f"unknown anchor_type: {self.anchor_type!r}")
        return errors

    def is_valid(self) -> bool:
        return not self.validate()

    # ── Serialization ───────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-serializable dict suitable for API responses or DB storage."""
        return {
            "signal_id": self.signal_id,
            "modality": self.modality,
            "signal_type": self.signal_type,
            "confidence": self.confidence,
            "extractor_id": self.extractor_id,
            "model_version": self.model_version,
            "value": self.value,
            "anchor": self.anchor,
            "anchor_type": self.anchor_type,
        }
