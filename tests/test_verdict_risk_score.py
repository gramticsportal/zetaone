"""VerdictService risk score formula tests."""

from __future__ import annotations

import sys
from pathlib import Path

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.services.verdict_service import VerdictService


def test_risk_score_zero_without_violations():
    svc = VerdictService()
    assert svc._calculate_risk_score([]) == 0.0
    out = svc.generate({"violations": [], "signals": []})
    assert out["risk_score"] == 0.0
    assert out["status"] == "COMPLIANT"


def test_risk_score_single_high_violation():
    svc = VerdictService()
    violations = [{"severity": "HIGH", "confidence": 0.95}]
    score = svc._calculate_risk_score(violations)
    assert score == 50.0


def test_risk_score_capped_at_100():
    svc = VerdictService()
    violations = [
        {"severity": "CRITICAL", "confidence": 0.99},
        {"severity": "CRITICAL", "confidence": 0.99},
    ]
    assert svc._calculate_risk_score(violations) == 100.0


def test_risk_score_low_confidence_multiplier():
    svc = VerdictService()
    violations = [{"severity": "HIGH", "confidence": 0.5}]
    # HIGH=50 * low conf mult 0.3 = 15
    assert svc._calculate_risk_score(violations) == 15.0


def test_status_thresholds():
    svc = VerdictService()
    assert svc._determine_status(0.0, []) == "COMPLIANT"
    assert svc._determine_status(35.0, [{}]) == "REVIEW_REQUIRED"
    assert svc._determine_status(75.0, [{}]) == "NON_COMPLIANT"
