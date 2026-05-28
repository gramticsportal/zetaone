#!/usr/bin/env python3
"""
Unit tests for the Tobacco and Nicotine policy.

- Policy ID: tobacco_nicotine (Meta Ads, Restricted Goods)
- OCR is the primary trigger; vision and embeddings are supporting only.
- Exceptions: smoking cessation / NRT must not trigger.
"""

from __future__ import annotations
import sys
import os
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schemas.models import Signal, SignalType, Asset
from pipeline.engine import CompliancePipeline


def _text_signal(text: str, bbox=None) -> Signal:
    return Signal(
        signal_id=str(uuid.uuid4()),
        signal_type=SignalType.TEXT,
        source_model="ocr_test",
        confidence=0.9,
        raw_data={"text": text},
        bounding_box=bbox or {"x": 0, "y": 0, "width": 100, "height": 20},
        detected_at=datetime.now(),
    )


def _vision_signal(label: str, confidence: float = 0.8) -> Signal:
    return Signal(
        signal_id=str(uuid.uuid4()),
        signal_type=SignalType.OBJECT,
        source_model="grounding_dino",
        confidence=confidence,
        raw_data={
            "type": "vision_object",
            "label": label,
            "confidence": confidence,
            "bbox": [5, 5, 40, 40],
            "model": "grounding_dino",
        },
        bounding_box={"x": 5, "y": 5, "width": 40, "height": 40},
        detected_at=datetime.now(),
    )


def _asset() -> Asset:
    return Asset(
        image_id=str(uuid.uuid4()),
        image_data=b"placeholder",
        filename="test.jpg",
        content_type="image/jpeg",
    )


def test_tobacco_violating_vape():
    """OCR: 'Buy premium vape cartridges today' -> expect tobacco_nicotine violation."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("Buy premium vape cartridges today")]
    violations = pipeline._check_rules(_asset(), signals)
    tobacco = [v for v in violations if v.rule_id == "tobacco_nicotine"]
    assert tobacco, "Expected tobacco_nicotine violation for vape promotion"
    assert tobacco[0].severity.value == "HIGH"
    text_ev = [e for e in tobacco[0].evidence if e.evidence_type == "text_match"]
    assert text_ev, "Expected text_match evidence"
    assert "vape" in text_ev[0].data.get("ocr_text", "").lower()


def test_tobacco_exception_cessation():
    """OCR: FDA-approved nicotine patch / quit smoking -> expect NO violation."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("FDA-approved nicotine patch to quit smoking")]
    violations = pipeline._check_rules(_asset(), signals)
    tobacco = [v for v in violations if v.rule_id == "tobacco_nicotine"]
    assert not tobacco, "Smoking cessation / NRT must NOT trigger tobacco_nicotine (exception)"


def test_tobacco_vision_only_no_violation():
    """Vision detects cigarette, no OCR -> expect NO violation (OCR is primary trigger)."""
    pipeline = CompliancePipeline()
    signals = [_vision_signal("cigarette", 0.85)]
    violations = pipeline._check_rules(_asset(), signals)
    tobacco = [v for v in violations if v.rule_id == "tobacco_nicotine"]
    assert not tobacco, "Vision-only must NOT trigger tobacco_nicotine (OCR is primary)"


def main():
    print("=" * 60)
    print("  Tobacco and Nicotine Policy - Test Suite")
    print("=" * 60)
    test_tobacco_violating_vape()
    print("  PASS - violating case (vape)")
    test_tobacco_exception_cessation()
    print("  PASS - allowed exception (quit smoking / NRT)")
    test_tobacco_vision_only_no_violation()
    print("  PASS - vision-only control")
    print("\n  All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
