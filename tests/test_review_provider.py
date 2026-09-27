"""Provider-neutral local-first advisory review."""

import json

import pytest

from zataone.schemas.llm_review import LlmFinalReviewV1, LocalReviewV1
from zataone.services import llm_final_review_service as review_mod


def _review(
    *,
    agreement: str = "aligns",
    cited: list[str] | None = None,
    status: str = "COMPLIANT",
    verdict: str = "likely_approved",
):
    return LlmFinalReviewV1(
        summary="Review summary",
        agreement_with_deterministic=agreement,
        rationale="Evidence supports the result.",
        cited_signal_ids=cited or [],
        recommended_compliance_status=status,
        recommended_verdict=verdict,
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
        lambda *a, **k: (
            _review(cited=["sig-1"], status="LIKELY_REJECTED", verdict="likely_rejected"),
            {"review_provider": "ollama"},
        ),
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


def test_cascade_keeps_a_local_flag_that_diverges_from_rules(monkeypatch):
    monkeypatch.setenv("ZATAONE_REVIEW_PROVIDER", "cascade")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(
        review_mod,
        "_advisory_json_from_ollama",
        lambda *a, **k: (
            _review(agreement="diverges", status="LIKELY_REJECTED", verdict="likely_rejected"),
            {"review_provider": "ollama", "review_model": "qwen3:4b"},
        ),
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
        model="gemini-test",
        max_toks=100,
        review_mode="advisory_second_read",
    )
    assert meta["review_provider"] == "ollama"
    assert gemini_called == []


def test_cascade_falls_back_when_local_output_is_invalid(monkeypatch):
    monkeypatch.setenv("ZATAONE_REVIEW_PROVIDER", "cascade")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def bad_local(*a, **k):
        raise review_mod.BadLlmReviewOutput("not json")

    monkeypatch.setattr(review_mod, "_advisory_json_from_ollama", bad_local)
    monkeypatch.setattr(
        review_mod,
        "_advisory_json_from_gemini",
        lambda *a, **k: _review(status="LIKELY_REJECTED", verdict="likely_rejected"),
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
    assert meta["review_fallback_reason"].startswith("local_failure:")


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


def test_cascade_sends_local_compliant_to_gemini(monkeypatch):
    monkeypatch.setenv("ZATAONE_REVIEW_PROVIDER", "cascade")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("ZATAONE_CASCADE_ESCALATE_COMPLIANT", raising=False)
    monkeypatch.setattr(
        review_mod,
        "_advisory_json_from_ollama",
        lambda *a, **k: (_review(), {"review_provider": "ollama"}),
    )
    monkeypatch.setattr(
        review_mod,
        "_advisory_json_from_gemini",
        lambda *a, **k: _review(status="LIKELY_REJECTED", verdict="likely_rejected"),
    )

    result, meta = review_mod._advisory_json_from_provider(
        _context(),
        system_prompt="review",
        model="gemini-test",
        max_toks=100,
        review_mode="advisory_second_read",
    )
    assert meta["review_provider"] == "gemini"
    assert meta["review_fallback_reason"] == "local_compliant_needs_second_read"
    assert result.recommended_compliance_status == "LIKELY_REJECTED"


def test_compliant_escalation_can_be_disabled(monkeypatch):
    monkeypatch.setenv("ZATAONE_CASCADE_ESCALATE_COMPLIANT", "0")
    assert (
        review_mod._review_rejection_reason(
            _review(), review_mode="advisory_second_read", user_msg=_context()
        )
        is None
    )


def test_local_review_contract_orders_reason_before_decision():
    schema = LocalReviewV1.model_json_schema()
    assert list(schema["properties"])[:3] == [
        "rationale",
        "agreement_with_deterministic",
        "recommended_compliance_status",
    ]
    assert schema["properties"]["recommended_compliance_status"]["enum"] == [
        "COMPLIANT",
        "REVIEW_REQUIRED",
        "LIKELY_REJECTED",
    ]
    assert "disclaimer" not in schema["properties"]


def test_local_review_expands_to_final_contract_and_clips_rationale():
    local = LocalReviewV1.model_validate(
        {
            "rationale": "x" * 900,
            "agreement_with_deterministic": "diverges",
            "recommended_compliance_status": "LIKELY_REJECTED",
            "recommended_verdict": "likely_rejected",
            "cited_signal_ids": ["sig-1"],
        }
    )
    final = local.to_final()
    assert len(final.rationale) == 400
    assert final.summary == final.rationale
    assert final.recommended_verdict == "likely_rejected"
    assert final.disclaimer


def test_local_review_rejects_values_outside_enum():
    with pytest.raises(ValueError):
        LocalReviewV1.model_validate(
            {
                "rationale": "r",
                "agreement_with_deterministic": "aligns",
                "recommended_compliance_status": "MAYBE",
                "recommended_verdict": "likely_approved",
            }
        )


def test_ollama_compact_request_uses_local_contract(monkeypatch):
    monkeypatch.delenv("OLLAMA_REVIEW_COMPACT", raising=False)
    sent = {}

    def fake_chat(messages, **kwargs):
        sent.update(kwargs, system=messages[0]["content"])
        return review_mod.ollama_mod.OllamaGeneration(
            text=json.dumps(
                {
                    "rationale": "Clause C1 is breached.",
                    "agreement_with_deterministic": "diverges",
                    "recommended_compliance_status": "LIKELY_REJECTED",
                    "recommended_verdict": "likely_rejected",
                    "cited_signal_ids": [],
                }
            ),
            model="qwen3:4b",
            latency_ms=5.0,
        )

    monkeypatch.setattr(review_mod.ollama_mod, "ollama_chat_detailed", fake_chat)
    review, meta = review_mod._advisory_json_from_ollama(
        _context(), system_prompt="base prompt", max_toks=4096
    )
    assert review.recommended_compliance_status == "LIKELY_REJECTED"
    assert meta["review_output_contract"] == "compact"
    cited = sent["response_format"]["properties"]["cited_signal_ids"]
    assert cited["items"]["enum"] == ["sig-1"]
    assert cited["maxItems"] == 1
    assert sent["options"]["num_predict"] <= 320
    assert sent["system"].startswith("base prompt")


def test_local_schema_forbids_citations_when_there_are_no_signals():
    schema = review_mod._local_output_schema(json.dumps({"signals": []}))
    assert schema["properties"]["cited_signal_ids"] == {"type": "array", "maxItems": 0}
