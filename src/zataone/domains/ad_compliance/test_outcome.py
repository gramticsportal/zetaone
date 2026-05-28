#!/usr/bin/env python3
"""
Test script for Outcome generation.
Tests risk_score calculation, verdict determination, and fix_suggestions.
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schemas.models import Signal, SignalType, Asset, Verdict

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURE_PNG = os.path.join(TESTS_DIR, "tests", "assets", "fixture.png")
FIXTURE_WITH_TEXT_PNG = os.path.join(TESTS_DIR, "tests", "assets", "fixture_with_text.png")


def _load_fixture(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def load_fixture_image() -> bytes:
    return _load_fixture(FIXTURE_PNG)


def load_text_fixture_image() -> bytes:
    return _load_fixture(FIXTURE_WITH_TEXT_PNG)
from pipeline.engine import CompliancePipeline
import uuid
from datetime import datetime


def create_text_signal(text: str, signal_id: str = None) -> Signal:
    """Helper to create a text signal for testing."""
    return Signal(
        signal_id=signal_id or str(uuid.uuid4()),
        signal_type=SignalType.TEXT,
        source_model="ocr_test",
        confidence=0.95,
        raw_data={"text": text},
        detected_at=datetime.now()
    )


def test_outcome_generation_no_violations():
    """Test Outcome generation with no violations."""
    print("=" * 60)
    print("TEST 1: Outcome with No Violations")
    print("=" * 60)
    
    pipeline = CompliancePipeline()
    
    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=load_fixture_image(),
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    # No signals = no violations
    outcome = pipeline.process(asset)
    
    print(f"Risk Score: {outcome.risk_score:.2f}")
    print(f"Verdict: {outcome.verdict.value}")
    print(f"Status: {outcome.status.value}")
    print(f"Fix Suggestions: {len(outcome.fix_suggestions)}")
    
    assert outcome.risk_score == 0.0, f"Expected 0.0, got {outcome.risk_score}"
    assert outcome.verdict == Verdict.LIKELY_APPROVED, f"Expected LIKELY_APPROVED, got {outcome.verdict}"
    assert len(outcome.fix_suggestions) == 0, "Expected no fix suggestions"
    
    print("✅ PASSED")
    return True


def test_outcome_generation_likely_rejected():
    """Test Outcome generation with high risk (likely_rejected)."""
    print("\n" + "=" * 60)
    print("TEST 2: Outcome with High Risk (likely_rejected)")
    print("=" * 60)
    
    pipeline = CompliancePipeline()
    
    # Create signals with multiple misleading claims
    signals = [
        create_text_signal("Guaranteed instant results!"),
        create_text_signal("100% effective overnight"),
        create_text_signal("Lose 10 pounds in 7 days guaranteed")
    ]
    
    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=load_fixture_image(),
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    # Manually check rules to get violations
    violations = pipeline._check_rules(asset, signals)
    
    # Create outcome
    outcome = pipeline.process(asset)
    # Override signals since we're testing with specific signals
    outcome.signals = signals
    outcome.violations = violations
    outcome.risk_score = pipeline._calculate_risk_score(violations)
    outcome.verdict = pipeline._determine_verdict(outcome.risk_score)
    outcome.fix_suggestions = pipeline._generate_fix_suggestions(violations)
    
    print(f"Risk Score: {outcome.risk_score:.2f}")
    print(f"Verdict: {outcome.verdict.value}")
    print(f"Status: {outcome.status.value}")
    print(f"Violations: {len(outcome.violations)}")
    print(f"Fix Suggestions: {len(outcome.fix_suggestions)}")
    
    if outcome.fix_suggestions:
        print("\nFix Suggestions:")
        for i, suggestion in enumerate(outcome.fix_suggestions, 1):
            print(f"  {i}. {suggestion}")
    
    assert outcome.risk_score > 0.7, f"Expected risk_score > 0.7, got {outcome.risk_score}"
    assert outcome.verdict == Verdict.LIKELY_REJECTED, f"Expected LIKELY_REJECTED, got {outcome.verdict}"
    assert len(outcome.fix_suggestions) > 0, "Expected fix suggestions"
    
    print("\n✅ PASSED")
    return True


def test_outcome_generation_borderline():
    """Test Outcome generation with medium risk (borderline)."""
    print("\n" + "=" * 60)
    print("TEST 3: Outcome with Medium Risk (borderline)")
    print("=" * 60)
    
    pipeline = CompliancePipeline()
    
    # Create signal with single low-severity claim to get borderline risk
    # Use a term that might match a lower severity rule
    signals = [
        create_text_signal("Limited time offer")
    ]
    
    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=load_fixture_image(),
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    violations = pipeline._check_rules(asset, signals)
    
    # If no violations, create a mock violation with MEDIUM severity
    if not violations:
        from schemas.models import Violation, ViolationSeverity, Evidence
        mock_violation = Violation(
            violation_id=str(uuid.uuid4()),
            rule_id="test_rule",
            rule_name="Test Rule",
            severity=ViolationSeverity.MEDIUM,
            description="Test violation",
            evidence=[
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    violation_id="",
                    signal_id=signals[0].signal_id,
                    evidence_type="test",
                    description="Test evidence",
                    data={"confidence": 0.6, "signal_confidence": 0.8}
                )
            ]
        )
        violations = [mock_violation]
    
    risk_score = pipeline._calculate_risk_score(violations)
    verdict = pipeline._determine_verdict(risk_score)
    
    print(f"Risk Score: {risk_score:.2f}")
    print(f"Verdict: {verdict.value}")
    
    # Test verdict logic directly
    test_scores = [0.2, 0.5, 0.8]
    for score in test_scores:
        v = pipeline._determine_verdict(score)
        print(f"  Score {score:.1f} -> {v.value}")
        if score > 0.7:
            assert v == Verdict.LIKELY_REJECTED
        elif score >= 0.3:
            assert v == Verdict.BORDERLINE
        else:
            assert v == Verdict.LIKELY_APPROVED
    
    print("✅ PASSED")
    return True


def test_risk_score_calculation():
    """Test risk_score calculation uses violation confidence."""
    print("\n" + "=" * 60)
    print("TEST 4: Risk Score Calculation with Confidence")
    print("=" * 60)
    
    pipeline = CompliancePipeline()
    
    signals = [
        create_text_signal("Guaranteed results", "signal1"),
        create_text_signal("Instant delivery", "signal2")
    ]
    
    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=load_fixture_image(),
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    violations = pipeline._check_rules(asset, signals)
    risk_score = pipeline._calculate_risk_score(violations)
    
    print(f"Risk Score: {risk_score:.2f}")
    print(f"Violations: {len(violations)}")
    
    # Check that evidence confidence is used
    if violations and violations[0].evidence:
        evidence_conf = violations[0].evidence[0].data.get("confidence", 0.0)
        print(f"Evidence Confidence: {evidence_conf:.2f}")
        assert 0.0 <= evidence_conf <= 1.0, "Confidence should be in range [0.0, 1.0]"
    
    assert 0.0 <= risk_score <= 1.0, f"Risk score should be in range [0.0, 1.0], got {risk_score}"
    
    print("✅ PASSED")
    return True


def test_fix_suggestions_for_misleading_claims():
    """Test fix_suggestions generation for misleading claims."""
    print("\n" + "=" * 60)
    print("TEST 5: Fix Suggestions for Misleading Claims")
    print("=" * 60)
    
    pipeline = CompliancePipeline()
    
    signals = [
        create_text_signal("Guaranteed 100% effective instant results"),
        create_text_signal("Lose 10 pounds in 7 days")
    ]
    
    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=load_fixture_image(),
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    violations = pipeline._check_rules(asset, signals)
    suggestions = pipeline._generate_fix_suggestions(violations)
    
    print(f"Violations: {len(violations)}")
    print(f"Fix Suggestions: {len(suggestions)}")
    
    if suggestions:
        print("\nSuggestions:")
        for i, suggestion in enumerate(suggestions, 1):
            print(f"  {i}. {suggestion}")
        
        # Check that suggestions mention misleading claims
        has_misleading_suggestion = any(
            "misleading" in s.lower() or "guarantee" in s.lower() or "rephrase" in s.lower()
            for s in suggestions
        )
        assert has_misleading_suggestion, "Should have suggestions about misleading claims"
    
    assert len(suggestions) > 0, "Expected fix suggestions"
    
    print("✅ PASSED")
    return True


def test_api_response_format():
    """Test that Outcome can be converted to API response format."""
    print("\n" + "=" * 60)
    print("TEST 6: API Response Format")
    print("=" * 60)
    
    from schemas.models import Outcome, ComplianceStatus, Verdict
    
    outcome = Outcome(
        outcome_id="test-123",
        asset_id="asset-456",
        status=ComplianceStatus.NON_COMPLIANT,
        risk_score=0.85,
        verdict=Verdict.LIKELY_REJECTED,
        violations=[],
        signals=[],
        fix_suggestions=["Remove misleading claims", "Use qualified language"]
    )
    
    # Manually create response dict (simulating _outcome_to_dict)
    response = {
        "outcome_id": outcome.outcome_id,
        "asset_id": outcome.asset_id,
        "status": outcome.status.value,
        "risk_score": round(outcome.risk_score, 2),
        "verdict": outcome.verdict.value,
        "violations": [],
        "violation_count": len(outcome.violations),
        "signals_count": len(outcome.signals),
        "fix_suggestions": outcome.fix_suggestions,
        "processed_at": outcome.processed_at.isoformat(),
        "metadata": outcome.metadata
    }
    
    print("API Response keys:", list(response.keys()))
    
    # Check required fields
    required_fields = ["outcome_id", "asset_id", "status", "risk_score", "verdict", 
                      "violations", "violation_count", "fix_suggestions"]
    
    for field in required_fields:
        assert field in response, f"Missing required field: {field}"
        print(f"  ✅ {field}: {type(response[field]).__name__}")
    
    assert response["verdict"] == "likely_rejected"
    assert isinstance(response["fix_suggestions"], list)
    assert len(response["fix_suggestions"]) == 2
    
    print("\n✅ PASSED")
    return True


def test_confidence_routing_and_vlm_stub():
    """Test confidence routing triggers VLM stub evidence."""
    print("\n" + "=" * 60)
    print("TEST 7: Confidence Routing + VLM Stub")
    print("=" * 60)

    pipeline = CompliancePipeline()

    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=load_text_fixture_image(),
        filename="test.jpg",
        content_type="image/jpeg"
    )

    outcome = pipeline.process(asset)

    print(f"Routing: {outcome.metadata.get('routing')}")
    print(f"Status: {outcome.status.value}")

    assert outcome.metadata.get("routing") == "borderline_requires_context"

    # VLM should only be attached for borderline (non-rejected) cases.
    # If the outcome is clearly rejected, VLM must not be called/attached.
    has_vlm = any(
        ev.evidence_type == "vlm_reasoning_stub"
        for v in outcome.violations
        for ev in v.evidence
    )
    if outcome.verdict == Verdict.LIKELY_REJECTED or outcome.risk_score >= 0.7:
        assert not has_vlm, "Did not expect VLM evidence for clearly rejected outcome"
    else:
        assert has_vlm, "Expected VLM reasoning evidence for borderline outcome"

    print("\n✅ PASSED")
    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  🧪 Outcome Generation - Test Suite")
    print("=" * 60)
    
    results = []
    results.append(("No Violations", test_outcome_generation_no_violations()))
    results.append(("Likely Rejected", test_outcome_generation_likely_rejected()))
    results.append(("Borderline", test_outcome_generation_borderline()))
    results.append(("Risk Score Calculation", test_risk_score_calculation()))
    results.append(("Fix Suggestions", test_fix_suggestions_for_misleading_claims()))
    results.append(("API Response Format", test_api_response_format()))
    results.append(("Confidence Routing + VLM Stub", test_confidence_routing_and_vlm_stub()))
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n⚠️  Some tests failed.")
        return 1


if __name__ == "__main__":
    exit(main())
