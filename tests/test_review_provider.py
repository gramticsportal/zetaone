"""Provider-neutral local-first advisory review."""

import json

from zataone.schemas.llm_review import LlmFinalReviewV1
from zataone.services import llm_final_review_service as review_mod


def _review(*, agreement: str = "aligns", cited: list[str] | None = None):
    return LlmFinalReviewV1(
        summary="Review summary",
        agreement_with_deterministic=agreement,
        rationale="Evidence supports the result.",
        cited_signal_ids=cited or [],
        recommended_compliance_status="COMPLIANT",
        recommended_verdict="likely_approved",
    )


def _context() -> str:
    return json.dumps(
        {
            "signals": [{"id": "sig-1"}],
            "violations": [],
            "deterministic_verdict": {"status": "COMPLIANT"},
        }
    )


def test_ollama_provider_does_not_require_gemini_key(monkeypatch):
    monkeypatch.setenv("ZATAONE_REVIEW_PROVIDER", "ollama")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        review_mod,
        "_advisory_json_from_ollama",
        lambda *a, **k: (
            _review(),
            {
                "review_provider": "ollama",
                "review_model": "qwen3:8b",
                "review_latency_ms": 12,
                "review_schema_valid": True,
            },
        ),
    )

    result, meta = review_mod._advisory_json_from_provider(
        _context(),
        system_prompt="review",
        model=None,
        max_toks=100,
        review_mode="advisory_second_read",
    )
    assert result.summary == "Review summary"
    assert meta["review_provider"] == "ollama"
    assert review_mod._llm_enabled() is True


def test_cascade_accepts_clear_local_review_without_gemini(monkeypatch):
    monkeypatch.setenv("ZATAONE_REVIEW_PROVIDER", "cascade")
    monkeypatch.setattr(
        review_mod,
        "_advisory_json_from_ollama",
        lambda *a, **k: (_review(cited=["sig-1"]), {"review_provider": "ollama"}),
    )
    gemini_called = []
    monkeypatch.setattr(
        review_mod,
        "_advisory_json_from_gemini",
        lambda *a, **k: gemini_called.append(True) or _review(),
    )

    _, meta = review_mod._advisory_json_from_provider(
        _context(),
        system_prompt="review",
        model=None,
        max_toks=100,
        review_mode="advisory_second_read",
    )
    assert meta["review_provider"] == "ollama"
    assert meta["review_primary_provider"] == "ollama"
    assert gemini_called == []


def test_cascade_falls_back_when_local_diverges(monkeypatch):
    monkeypatch.setenv("ZATAONE_REVIEW_PROVIDER", "cascade")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        review_mod,
        "_advisory_json_from_ollama",
        lambda *a, **k: (
            _review(agreement="diverges"),
            {"review_provider": "ollama", "review_model": "qwen3:8b"},
        ),
    )
    monkeypatch.setattr(
        review_mod,
        "_advisory_json_from_gemini",
        lambda *a, **k: _review(agreement="aligns"),
    )

    _, meta = review_mod._advisory_json_from_provider(
        _context(),
        system_prompt="review",
        model="gemini-test",
        max_toks=100,
        review_mode="advisory_second_read",
    )
    assert meta["review_provider"] == "gemini"
    assert meta["review_primary_provider"] == "ollama"
    assert meta["review_fallback_reason"] == "model_diverges_from_deterministic"


def test_cascade_rejects_invented_signal_id(monkeypatch):
    review = _review(cited=["made-up"])
    assert (
        review_mod._review_rejection_reason(
            review,
            review_mode="advisory_second_read",
            user_msg=_context(),
        )
        == "invented_signal_citation"
    )


def test_review_schema_normalizes_invalid_primary_verdicts():
    review = LlmFinalReviewV1(
        summary="s",
        agreement_with_deterministic="aligns",
        rationale="r",
        recommended_compliance_status="not-a-status",
        recommended_verdict="not-a-verdict",
    )
    assert review.recommended_compliance_status is None
    assert review.recommended_verdict is None
