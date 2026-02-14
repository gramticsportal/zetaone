#!/usr/bin/env python3
"""
Unit tests for the Medical / Health Claims policy rule.

Scope:
- OCR text (SignalType.TEXT) is the ONLY trigger for violations.
- Embedding similarity signals may appear as supporting evidence only.
"""

import sys
import os
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schemas.models import Signal, SignalType, Asset
from pipeline.engine import CompliancePipeline


def create_text_signal(text: str, bbox=None, signal_id: str | None = None) -> Signal:
    return Signal(
        signal_id=signal_id or str(uuid.uuid4()),
        signal_type=SignalType.TEXT,
        source_model="ocr_test",
        confidence=0.95,
        raw_data={"text": text},
        bounding_box=bbox,
        detected_at=datetime.now(),
    )


def create_embedding_signal(regulation: str, score: float = 0.8) -> Signal:
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


def test_medical_policy_violation():
    pipeline = CompliancePipeline()

    bbox = {"x": 10, "y": 20, "width": 100, "height": 30}
    signals = [
        create_text_signal("Heal chronic back pain fast", bbox=bbox),
        # Supporting evidence only (must not trigger by itself)
        create_embedding_signal("medical_health_claims", 0.75),
    ]

    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=b"fake_image",  # not used by _check_rules
        filename="test.jpg",
        content_type="image/jpeg",
    )

    violations = pipeline._check_rules(asset, signals)
    medical = [v for v in violations if v.rule_id == "medical_health_claims"]
    assert medical, "Expected a medical_health_claims violation"
    v = medical[0]
    assert v.severity.value == "HIGH"

    # Evidence should include OCR text + bbox
    text_evidence = [e for e in v.evidence if e.evidence_type == "text_match"]
    assert text_evidence, "Expected text_match evidence"
    assert text_evidence[0].data.get("ocr_text") == "Heal chronic back pain fast"
    assert text_evidence[0].data.get("bbox") == bbox

    # If embedding similarity signal is present, it should be included as evidence
    emb_evidence = [e for e in v.evidence if e.evidence_type == "image_embedding_similarity"]
    assert emb_evidence, "Expected embedding similarity evidence when signal is present"


def test_medical_policy_non_violation_without_context():
    """
    Contains a claim-like verb ("heal") but no medical/health context keywords.
    Must not trigger the medical_health_claims violation.
    """
    pipeline = CompliancePipeline()

    signals = [
        create_text_signal("Heal your home with our cleaning spray", bbox={"x": 1, "y": 1, "width": 10, "height": 10}),
        # Even if an embedding signal exists, it must not create a violation alone
        create_embedding_signal("medical_health_claims", 0.75),
    ]

    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=b"fake_image",
        filename="test.jpg",
        content_type="image/jpeg",
    )

    violations = pipeline._check_rules(asset, signals)
    medical = [v for v in violations if v.rule_id == "medical_health_claims"]
    assert not medical, "Did not expect a medical_health_claims violation without medical context"


def main():
    print("=" * 60)
    print("  🧪 Medical / Health Claims Policy - Test Suite")
    print("=" * 60)

    test_medical_policy_violation()
    print("✅ PASS - violating example")

    test_medical_policy_non_violation_without_context()
    print("✅ PASS - non-violating example")

    print("\n🎉 All tests passed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

