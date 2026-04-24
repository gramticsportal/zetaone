"""LLM final review Pydantic schema."""

import uuid

from zataone.schemas.llm_review import build_review_context, LlmFinalReviewV1


def test_build_review_context():
    ctx = build_review_context(
        schema_version="1.0",
        asset_id=uuid.uuid4(),
        domain="ad_compliance",
        asset_type="image",
        deterministic_verdict={"verdict": "borderline", "risk_score": 0.4},
        signals=[{"id": "a", "signal_type": "TEXT", "value": {}, "confidence": 0.9, "extractor_id": "x"}],
        violations=[],
        advisory_vlm={
            "inspection": "A test image.",
            "prompt_focus": "test",
            "skipped": False,
            "skipped_reason": None,
        },
    )
    assert ctx["vlm_image_summary"] == "A test image."
    assert ctx["advisory_vlm"]["inspection"] == "A test image."
    assert "deterministic_verdict" in ctx


def test_llm_final_review_v1_flexible_agreement():
    m = LlmFinalReviewV1(
        summary="s",
        agreement_with_deterministic="MOSTLY ALIGNS",
        rationale="r",
    )
    assert m.agreement_with_deterministic == "mostly_aligns"
