#!/usr/bin/env python3
"""
Test: vlm_called_only_for_borderline

- Mock the VLM API call
- Verify VLM is called when routing is borderline (and OCR-based violations exist)
- Verify VLM is NOT called when routing is clean or rejected
- Verify returned reasoning text is attached to evidence
"""

from __future__ import annotations
import os
import sys
import uuid
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from schemas.models import Asset, Signal, SignalType, Verdict
from pipeline.engine import CompliancePipeline


def _text_signal(text: str, conf: float = 0.95) -> Signal:
    return Signal(
        signal_id=str(uuid.uuid4()),
        signal_type=SignalType.TEXT,
        source_model="ocr_test",
        confidence=conf,
        raw_data={"text": text},
        detected_at=datetime.now(),
    )


def test_vlm_called_only_for_borderline():
    import models.vlm as vlm_mod

    calls = {"n": 0}

    def fake_analyze_image_context(*args, **kwargs):
        calls["n"] += 1
        return "Short VLM explanation."

    orig = vlm_mod.analyze_image_context
    vlm_mod.analyze_image_context = fake_analyze_image_context
    try:
        pipeline = CompliancePipeline()
        asset = Asset(
            image_id=str(uuid.uuid4()),
            image_data=b"fake_image",
            filename="test.png",
            content_type="image/png",
        )

        # Build OCR-based violations via real rule check (no mocking rules/pipeline)
        signals = [_text_signal("Guaranteed instant results", conf=0.2)]
        violations = pipeline._check_rules(asset, signals)
        assert violations, "Expected at least one OCR-based violation for test setup"

        # 1) Borderline: should call VLM and attach evidence
        calls["n"] = 0
        pipeline._maybe_attach_vlm_reasoning(
            asset=asset,
            signals=signals,
            violations=violations,
            routing_flag="borderline_requires_context",
            verdict=Verdict.BORDERLINE,
            risk_score=0.5,
        )
        assert calls["n"] == 1, "Expected VLM call for borderline routing"
        has_reasoning = any(
            ev.evidence_type == "vlm_reasoning_stub" and ev.data.get("explanation") == "Short VLM explanation."
            for v in violations
            for ev in v.evidence
        )
        assert has_reasoning, "Expected VLM reasoning evidence attached"

        # 2) Clean: should not call VLM
        calls["n"] = 0
        pipeline._maybe_attach_vlm_reasoning(
            asset=asset,
            signals=signals,
            violations=violations,
            routing_flag=None,
            verdict=Verdict.LIKELY_APPROVED,
            risk_score=0.0,
        )
        assert calls["n"] == 0, "Did not expect VLM call when routing is not borderline"

        # 3) Rejected: should not call VLM even if routing is borderline
        calls["n"] = 0
        pipeline._maybe_attach_vlm_reasoning(
            asset=asset,
            signals=signals,
            violations=violations,
            routing_flag="borderline_requires_context",
            verdict=Verdict.LIKELY_REJECTED,
            risk_score=0.9,
        )
        assert calls["n"] == 0, "Did not expect VLM call for clearly rejected outcome"
    finally:
        vlm_mod.analyze_image_context = orig


def main():
    test_vlm_called_only_for_borderline()
    print("✅ PASS - vlm_called_only_for_borderline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

