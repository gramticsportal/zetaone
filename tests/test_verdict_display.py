"""Display vs deterministic verdict elevation."""

import sys
from pathlib import Path

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.core.verdict_display import apply_display_verdict, enrich_api_verdict_payload


def test_zero_signals_elevates_to_review_required():
    verdict = {"status": "COMPLIANT", "verdict": "likely_approved", "risk_score": 0.0, "metadata": {}}
    apply_display_verdict(verdict, signal_count=0)
    assert verdict["status"] == "REVIEW_REQUIRED"
    assert verdict["metadata"]["elevated_by_advisory"] is True
    assert verdict["metadata"]["deterministic_compliance_status"] == "COMPLIANT"
    assert verdict["metadata"]["override_reason"] == "no_extractor_signals"


def test_diverges_elevates():
    verdict = {
        "status": "COMPLIANT",
        "verdict": "likely_approved",
        "metadata": {},
        "llm_final_review": {"agreement_with_deterministic": "diverges"},
    }
    apply_display_verdict(verdict, signal_count=5)
    assert verdict["status"] == "REVIEW_REQUIRED"
    assert verdict["metadata"]["override_reason"] == "advisory_diverges_from_deterministic"


def test_aligns_no_elevation():
    verdict = {
        "status": "COMPLIANT",
        "verdict": "likely_approved",
        "metadata": {},
        "llm_final_review": {"agreement_with_deterministic": "aligns"},
    }
    apply_display_verdict(verdict, signal_count=3)
    assert verdict["status"] == "COMPLIANT"
    assert verdict["metadata"]["elevated_by_advisory"] is False


def test_enrich_api_payload():
    result = {
        "status": "REVIEW_REQUIRED",
        "verdict": "borderline",
        "metadata": {
            "deterministic_compliance_status": "COMPLIANT",
            "deterministic_verdict": "likely_approved",
            "elevated_by_advisory": True,
            "verdict_source": "advisory_escalation",
            "override_reason": "no_extractor_signals",
            "pipeline_mode": "full",
            "signal_count": 0,
        },
    }
    out = enrich_api_verdict_payload(result)
    assert out["display_compliance_status"] == "REVIEW_REQUIRED"
    assert out["deterministic_compliance_status"] == "COMPLIANT"
    assert out["elevated_by_advisory"] is True
