#!/usr/bin/env python3
"""
Unit tests for the Financial Products and Guarantees policy.

- Policy ID: financial_products_and_guarantees (Meta Ads, Financial Products)
- OCR is the only trigger; vision and embeddings are supporting only.
- Exceptions: informational, educational, financial literacy.
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


def test_financial_products_violating_guarantees():
    """OCR: 'Guaranteed loan approval — no risk, apply now' -> expect financial_products_and_guarantees violation."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("Guaranteed loan approval — no risk, apply now")]
    violations = pipeline._check_rules(_asset(), signals)
    financial = [v for v in violations if v.rule_id == "financial_products_and_guarantees"]
    assert financial, "Expected financial_products_and_guarantees violation for guaranteed approval + no risk"
    assert financial[0].severity.value == "HIGH"
    text_ev = [e for e in financial[0].evidence if e.evidence_type == "text_match"]
    assert text_ev, "Expected text_match evidence"
    ocr = text_ev[0].data.get("ocr_text", "")
    assert "guaranteed" in ocr.lower() or "no risk" in ocr.lower()


def test_financial_products_informational_no_violation():
    """OCR: 'Learn how mortgages work and what affects interest rates' -> expect NO violation."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("Learn how mortgages work and what affects interest rates")]
    violations = pipeline._check_rules(_asset(), signals)
    financial = [v for v in violations if v.rule_id == "financial_products_and_guarantees"]
    assert not financial, "Informational/educational content must NOT trigger financial_products_and_guarantees"


def test_financial_products_vision_only_no_violation():
    """Vision detects money/cash, no OCR -> expect NO violation (OCR is primary trigger)."""
    pipeline = CompliancePipeline()
    signals = [_vision_signal("money", 0.85), _vision_signal("cash", 0.8)]
    violations = pipeline._check_rules(_asset(), signals)
    financial = [v for v in violations if v.rule_id == "financial_products_and_guarantees"]
    assert not financial, "Vision-only must NOT trigger financial_products_and_guarantees (OCR is primary)"


def main():
    print("=" * 60)
    print("  Financial Products and Guarantees - Test Suite")
    print("=" * 60)
    test_financial_products_violating_guarantees()
    print("  PASS - violating case (guaranteed approval, no risk)")
    test_financial_products_informational_no_violation()
    print("  PASS - non-violating informational (learn how mortgages work)")
    test_financial_products_vision_only_no_violation()
    print("  PASS - vision-only control")
    print("\n  All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
