#!/usr/bin/env python3
"""
Unit tests for the Gambling and Betting policy.

- Policy ID: gambling (Meta Ads, Restricted Goods)
- OCR is the only trigger; vision and embeddings are supporting only.
- Exceptions: informational, non-monetary / for-fun games.
"""

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


def test_gambling_violating_real_money():
    """OCR: 'Bet real money on tonight's game' -> expect gambling violation."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("Bet real money on tonight's game")]
    violations = pipeline._check_rules(_asset(), signals)
    gambling = [v for v in violations if v.rule_id == "gambling"]
    assert gambling, "Expected gambling violation for real money betting"
    assert gambling[0].severity.value == "HIGH"
    text_ev = [e for e in gambling[0].evidence if e.evidence_type == "text_match"]
    assert text_ev, "Expected text_match evidence"


def test_gambling_non_violating_free_fun():
    """OCR: 'Play free card games for fun' -> expect NO violation."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("Play free card games for fun")]
    violations = pipeline._check_rules(_asset(), signals)
    gambling = [v for v in violations if v.rule_id == "gambling"]
    assert not gambling, "Free/fun language alone must NOT trigger gambling (no real-money promotion)"


def test_gambling_vision_only_no_violation():
    """Vision detects cards/chips, no OCR -> expect NO violation (OCR is primary trigger)."""
    pipeline = CompliancePipeline()
    signals = [_vision_signal("cards", 0.85), _vision_signal("chips", 0.8)]
    violations = pipeline._check_rules(_asset(), signals)
    gambling = [v for v in violations if v.rule_id == "gambling"]
    assert not gambling, "Vision-only must NOT trigger gambling (OCR is primary)"


def main():
    print("=" * 60)
    print("  Gambling and Betting Policy - Test Suite")
    print("=" * 60)
    test_gambling_violating_real_money()
    print("  PASS - violating case (real money bet)")
    test_gambling_non_violating_free_fun()
    print("  PASS - non-violating (free card games for fun)")
    test_gambling_vision_only_no_violation()
    print("  PASS - vision-only control")
    print("\n  All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
