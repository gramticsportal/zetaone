#!/usr/bin/env python3
"""
Unit tests for the Fraud, Scams, and Deceptive Practices policy.

- Policy ID: fraud_scams_deceptive (Meta Ads)
- OCR is the only trigger; vision and embeddings are supporting evidence only.
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


def _embedding_signal(regulation: str, score: float = 0.75) -> Signal:
    return Signal(
        signal_id=str(uuid.uuid4()),
        signal_type=SignalType.SCENE,
        source_model="siglip",
        confidence=score,
        raw_data={
            "type": "image_embedding_similarity",
            "regulation": regulation,
            "score": score,
            "model": "siglip",
        },
        bounding_box=None,
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
            "bbox": [10, 10, 50, 50],
            "model": "grounding_dino",
        },
        bounding_box={"x": 10, "y": 10, "width": 50, "height": 50},
        detected_at=datetime.now(),
    )


def _asset(image_data: bytes = b"placeholder") -> Asset:
    return Asset(
        image_id=str(uuid.uuid4()),
        image_data=image_data,
        filename="test.jpg",
        content_type="image/jpeg",
    )


def test_fraud_violating_guaranteed_profit_and_urgency():
    """OCR text includes guaranteed profit + urgency → expect fraud_scams_deceptive violation."""
    pipeline = CompliancePipeline()
    signals = [
        _text_signal("Guaranteed income - Act now! Limited time only."),
        _embedding_signal("fraud_scams_deceptive", 0.7),
    ]
    violations = pipeline._check_rules(_asset(), signals)
    fraud = [v for v in violations if v.rule_id == "fraud_scams_deceptive"]
    assert fraud, "Expected fraud_scams_deceptive violation when OCR has guaranteed profit + urgency"
    assert fraud[0].severity.value == "HIGH"
    text_ev = [e for e in fraud[0].evidence if e.evidence_type == "text_match"]
    assert text_ev, "Expected text_match evidence"
    assert "guaranteed" in text_ev[0].data.get("ocr_text", "").lower() or "act now" in text_ev[0].data.get("ocr_text", "").lower()


def test_fraud_non_violating_generic_marketing():
    """Generic marketing copy with no deception → no fraud_scams_deceptive violation."""
    pipeline = CompliancePipeline()
    signals = [
        _text_signal("Summer sale - 20% off. Free shipping over $50. Shop our new arrivals."),
    ]
    violations = pipeline._check_rules(_asset(), signals)
    fraud = [v for v in violations if v.rule_id == "fraud_scams_deceptive"]
    assert not fraud, "Expected NO fraud_scams_deceptive for generic marketing without deception"


def test_fraud_vision_only_no_violation():
    """Vision detects money/cash but no OCR fraud language → no fraud violation (vision must not trigger)."""
    pipeline = CompliancePipeline()
    signals = [
        _vision_signal("money", 0.85),
        _vision_signal("cash", 0.8),
        _embedding_signal("fraud_scams_deceptive", 0.75),
    ]
    violations = pipeline._check_rules(_asset(), signals)
    fraud = [v for v in violations if v.rule_id == "fraud_scams_deceptive"]
    assert not fraud, "Vision and embedding alone must NOT trigger fraud_scams_deceptive (OCR is primary trigger)"


def main():
    print("=" * 60)
    print("  Fraud, Scams, and Deceptive Practices - Test Suite")
    print("=" * 60)
    test_fraud_violating_guaranteed_profit_and_urgency()
    print("  PASS - violating case (guaranteed profit + urgency)")
    test_fraud_non_violating_generic_marketing()
    print("  PASS - non-violating control (generic marketing)")
    test_fraud_vision_only_no_violation()
    print("  PASS - vision-only control (no OCR fraud)")
    print("\n  All tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
