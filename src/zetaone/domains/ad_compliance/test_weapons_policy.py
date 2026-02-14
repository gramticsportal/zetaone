#!/usr/bin/env python3
"""
Unit tests for the Weapons, Ammunition, Explosives policy.

- Policy ID: weapons_ammunition_explosives (Meta Ads, Restricted Goods)
- Vision is the primary trigger; OCR and embeddings are supporting evidence only.
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


def _vision_signal(label: str, confidence: float = 0.85) -> Signal:
    return Signal(
        signal_id=str(uuid.uuid4()),
        signal_type=SignalType.OBJECT,
        source_model="grounding_dino",
        confidence=confidence,
        raw_data={
            "type": "vision_object",
            "label": label,
            "confidence": confidence,
            "bbox": [10, 10, 50, 50],
            "model": "grounding_dino",
        },
        bounding_box={"x": 10, "y": 10, "width": 50, "height": 50},
        detected_at=datetime.now(),
    )


def _asset() -> Asset:
    return Asset(
        image_id=str(uuid.uuid4()),
        image_data=b"placeholder",
        filename="test.jpg",
        content_type="image/jpeg",
    )


def test_weapons_vision_triggered_violation():
    """Vision detects weapon -> expect weapons_ammunition_explosives violation."""
    pipeline = CompliancePipeline()
    signals = [_vision_signal("weapon", 0.9)]
    violations = pipeline._check_rules(_asset(), signals)
    weapons = [v for v in violations if v.rule_id == "weapons_ammunition_explosives"]
    assert weapons, "Expected weapons_ammunition_explosives violation when vision detects weapon"
    assert weapons[0].severity.value == "HIGH"
    vision_ev = [e for e in weapons[0].evidence if e.evidence_type == "vision_object"]
    assert vision_ev, "Expected vision_object evidence"
    assert vision_ev[0].data.get("label") == "weapon"


def test_weapons_ocr_only_no_violation():
    """OCR mentions 'knife set for cooking' with no weapon vision -> expect NO violation."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("Knife set for cooking - best quality")]
    violations = pipeline._check_rules(_asset(), signals)
    weapons = [v for v in violations if v.rule_id == "weapons_ammunition_explosives"]
    assert not weapons, "OCR-only (no prohibited sale language, no vision) must NOT trigger weapons policy"


def test_weapons_ocr_only_sale_language_no_violation():
    """OCR has 'buy gun' but no vision detection -> expect NO violation (vision is primary trigger)."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("Buy gun here - best prices")]
    violations = pipeline._check_rules(_asset(), signals)
    weapons = [v for v in violations if v.rule_id == "weapons_ammunition_explosives"]
    assert not weapons, "OCR-only must NOT trigger weapons policy; vision is the primary trigger"


def test_weapons_vision_negative_control():
    """No weapon vision, no OCR -> expect NO violation."""
    pipeline = CompliancePipeline()
    signals = [_vision_signal("money", 0.8), _vision_signal("cash", 0.75)]
    violations = pipeline._check_rules(_asset(), signals)
    weapons = [v for v in violations if v.rule_id == "weapons_ammunition_explosives"]
    assert not weapons, "No weapon vision must NOT trigger weapons_ammunition_explosives"


def main():
    print("=" * 60)
    print("  Weapons, Ammunition, Explosives - Test Suite")
    print("=" * 60)
    test_weapons_vision_triggered_violation()
    print("  PASS - vision-triggered violation")
    test_weapons_ocr_only_no_violation()
    print("  PASS - OCR-only non-violation (knife set for cooking)")
    test_weapons_ocr_only_sale_language_no_violation()
    print("  PASS - OCR-only sale language does not trigger (vision primary)")
    test_weapons_vision_negative_control()
    print("  PASS - vision-negative control")
    print("\n  All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
