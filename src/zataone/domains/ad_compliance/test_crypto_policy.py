#!/usr/bin/env python3
"""
Unit tests for the Cryptocurrency Services policy.

- Policy ID: cryptocurrency_services (Meta Ads, Financial Products)
- OCR is the only trigger; vision and embeddings are supporting only.
- Exceptions: educational, informational, news, security/risk disclosures.
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


def test_crypto_violating_trade_promotion():
    """OCR: 'Trade crypto instantly on our exchange — buy Bitcoin today' -> expect cryptocurrency_services violation."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("Trade crypto instantly on our exchange — buy Bitcoin today")]
    violations = pipeline._check_rules(_asset(), signals)
    crypto = [v for v in violations if v.rule_id == "cryptocurrency_services"]
    assert crypto, "Expected cryptocurrency_services violation for crypto exchange + buy Bitcoin"
    assert crypto[0].severity.value == "HIGH"
    text_ev = [e for e in crypto[0].evidence if e.evidence_type == "text_match"]
    assert text_ev, "Expected text_match evidence"
    ocr = text_ev[0].data.get("ocr_text", "")
    assert "crypto" in ocr.lower() or "bitcoin" in ocr.lower()


def test_crypto_informational_no_violation():
    """OCR: 'Learn how blockchain technology works and why it matters' -> expect NO violation."""
    pipeline = CompliancePipeline()
    signals = [_text_signal("Learn how blockchain technology works and why it matters")]
    violations = pipeline._check_rules(_asset(), signals)
    crypto = [v for v in violations if v.rule_id == "cryptocurrency_services"]
    assert not crypto, "Informational/educational content must NOT trigger cryptocurrency_services"


def test_crypto_vision_only_no_violation():
    """Vision detects money/coins, no OCR -> expect NO violation (OCR is primary trigger)."""
    pipeline = CompliancePipeline()
    signals = [_vision_signal("money", 0.85), _vision_signal("cash", 0.8)]
    violations = pipeline._check_rules(_asset(), signals)
    crypto = [v for v in violations if v.rule_id == "cryptocurrency_services"]
    assert not crypto, "Vision-only must NOT trigger cryptocurrency_services (OCR is primary)"


def main():
    print("=" * 60)
    print("  Cryptocurrency Services Policy - Test Suite")
    print("=" * 60)
    test_crypto_violating_trade_promotion()
    print("  PASS - violating case (trade crypto, buy Bitcoin)")
    test_crypto_informational_no_violation()
    print("  PASS - informational exception (learn how blockchain works)")
    test_crypto_vision_only_no_violation()
    print("  PASS - vision-only control")
    print("\n  All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
