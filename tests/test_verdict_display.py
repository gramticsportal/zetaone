"""Display vs deterministic verdict elevation."""

import sys
from pathlib import Path

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.core.verdict_display import apply_display_verdict, enrich_api_verdict_payload


def test_zero_signals_elevates_when_rule_engine_ran_no_llm(monkeypatch):
    monkeypatch.setenv("ZATAONE_VERDICT_AUTHORITY", "advisory")
    verdict = {"status": "COMPLIANT", "verdict": "likely_approved", "risk_score": 0.0, "metadata": {}}
    apply_display_verdict(
        verdict, signal_count=0, pipeline_mode="full", policy_engine_ran=True
    )
    assert verdict["status"] == "REVIEW_REQUIRED"
    assert verdict["metadata"]["elevated_by_advisory"] is True
    assert verdict["metadata"]["deterministic_compliance_status"] == "COMPLIANT"
    assert verdict["metadata"]["override_reason"] == "no_extractor_signals"


def test_fast_mode_uses_advisory_recommendation():
    verdict = {
        "status": "PENDING_ADVISORY",
        "verdict": "pending_advisory",
        "metadata": {"pipeline_mode": "fast", "policy_engine_ran": False},
        "llm_final_review": {
            "agreement_with_deterministic": "diverges",
            "recommended_compliance_status": "REVIEW_REQUIRED",
            "recommended_verdict": "borderline",
        },
    }
    apply_display_verdict(verdict, signal_count=0, pipeline_mode="fast", policy_engine_ran=False)
    assert verdict["status"] == "REVIEW_REQUIRED"
    assert verdict["metadata"]["verdict_authority"] == "advisory"
    assert verdict["metadata"]["verdict_source"] == "advisory"


def test_fast_mode_likely_rejected_from_advisory():
    verdict = {
        "status": "PENDING_ADVISORY",
        "verdict": "pending_advisory",
        "metadata": {},
        "llm_final_review": {
            "recommended_compliance_status": "LIKELY_REJECTED",
            "recommended_verdict": "likely_rejected",
        },
    }
    apply_display_verdict(verdict, signal_count=0, pipeline_mode="fast", policy_engine_ran=False)
    assert verdict["status"] == "LIKELY_REJECTED"
    assert verdict["verdict"] == "likely_rejected"


def test_full_llm_primary_overrides_deterministic_on_diverge(monkeypatch):
    monkeypatch.setenv("ZATAONE_VERDICT_AUTHORITY", "advisory")
    verdict = {
        "status": "NON_COMPLIANT",
        "verdict": "likely_rejected",
        "metadata": {},
        "llm_final_review": {
            "agreement_with_deterministic": "diverges",
            "recommended_compliance_status": "COMPLIANT",
            "recommended_verdict": "likely_approved",
            "summary": "Academic slide, not political ad.",
        },
    }
    apply_display_verdict(verdict, signal_count=5, pipeline_mode="full", policy_engine_ran=True)
    assert verdict["status"] == "COMPLIANT"
    assert verdict["verdict"] == "likely_approved"
    assert verdict["metadata"]["verdict_authority"] == "advisory"
    assert verdict["metadata"]["verdict_source"] == "advisory"
    assert verdict["metadata"]["deterministic_compliance_status"] == "NON_COMPLIANT"
    assert verdict["metadata"]["deterministic_verdict"] == "likely_rejected"


def test_deterministic_authority_mode_preserves_rule_engine_display(monkeypatch):
    monkeypatch.setenv("ZATAONE_VERDICT_AUTHORITY", "deterministic")
    verdict = {
        "status": "COMPLIANT",
        "verdict": "likely_approved",
        "metadata": {},
        "llm_final_review": {"agreement_with_deterministic": "diverges"},
    }
    apply_display_verdict(verdict, signal_count=5, pipeline_mode="full", policy_engine_ran=True)
    assert verdict["status"] == "REVIEW_REQUIRED"
    assert verdict["metadata"]["override_reason"] == "advisory_diverges_from_deterministic"
    assert verdict["metadata"]["verdict_authority"] == "deterministic"


def test_aligns_uses_llm_when_recommended_present(monkeypatch):
    monkeypatch.setenv("ZATAONE_VERDICT_AUTHORITY", "advisory")
    verdict = {
        "status": "NON_COMPLIANT",
        "verdict": "likely_rejected",
        "metadata": {},
        "llm_final_review": {
            "agreement_with_deterministic": "aligns",
            "recommended_compliance_status": "LIKELY_REJECTED",
            "recommended_verdict": "likely_rejected",
        },
    }
    apply_display_verdict(verdict, signal_count=3, pipeline_mode="full", policy_engine_ran=True)
    assert verdict["status"] == "LIKELY_REJECTED"
    assert verdict["metadata"]["verdict_source"] == "advisory"


def test_enrich_api_payload():
    result = {
        "status": "REVIEW_REQUIRED",
        "verdict": "borderline",
        "metadata": {
            "deterministic_compliance_status": "COMPLIANT",
            "deterministic_verdict": "likely_approved",
            "elevated_by_advisory": True,
            "verdict_source": "advisory",
            "verdict_authority": "advisory",
            "override_reason": "advisory_policy_divergence",
            "pipeline_mode": "fast",
            "policy_engine_ran": False,
            "signal_count": 0,
        },
    }
    out = enrich_api_verdict_payload(result)
    assert out["display_compliance_status"] == "REVIEW_REQUIRED"
    assert out["deterministic_compliance_status"] == "COMPLIANT"
    assert out["policy_engine_ran"] is False
    assert out["verdict_authority"] == "advisory"
