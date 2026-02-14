#!/usr/bin/env python3
"""
Test script for the "Misleading or Exaggerated Claims" rule.
Tests rule detection, confidence scoring, and Signal-to-Violation mapping.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schemas.models import Signal, SignalType, Asset
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


def test_keyword_detection():
    """Test keyword-based detection."""
    print("=" * 60)
    print("TEST 1: Keyword Detection")
    print("=" * 60)
    
    pipeline = CompliancePipeline()
    
    # Create test signals with misleading claims
    signals = [
        create_text_signal("Guaranteed to work instantly!"),
        create_text_signal("100% effective overnight"),
        create_text_signal("Miracle cure for all problems")
    ]
    
    # Create dummy asset
    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=b"fake_image",
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    # Check rules
    violations = pipeline._check_rules(asset, signals)
    
    # Find misleading claims violation
    misleading_violations = [v for v in violations if v.rule_id == "misleading_exaggerated_claims"]
    
    print(f"Total violations: {len(violations)}")
    print(f"Misleading claims violations: {len(misleading_violations)}")
    
    if misleading_violations:
        violation = misleading_violations[0]
        print(f"\n✅ Violation detected:")
        print(f"   Rule: {violation.rule_name}")
        print(f"   Severity: {violation.severity.value}")
        print(f"   Evidence count: {len(violation.evidence)}")
        
        for i, evidence in enumerate(violation.evidence, 1):
            print(f"\n   Evidence {i}:")
            print(f"     Signal ID: {evidence.signal_id}")
            print(f"     Description: {evidence.description}")
            print(f"     Confidence: {evidence.data.get('confidence', 'N/A')}")
            print(f"     Matched term: {evidence.data.get('matched_term', 'N/A')}")
        
        return True
    else:
        print("\n❌ No violation detected (expected at least one)")
        return False


def test_pattern_detection():
    """Test pattern-based detection (e.g., 'lose X days')."""
    print("\n" + "=" * 60)
    print("TEST 2: Pattern Detection")
    print("=" * 60)
    
    pipeline = CompliancePipeline()
    
    # Create test signals with pattern matches
    signals = [
        create_text_signal("Lose 10 days with our program!"),
        create_text_signal("Lose 5 pounds in 7 days guaranteed"),
        create_text_signal("100% guaranteed results")
    ]
    
    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=b"fake_image",
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    violations = pipeline._check_rules(asset, signals)
    misleading_violations = [v for v in violations if v.rule_id == "misleading_exaggerated_claims"]
    
    print(f"Total violations: {len(violations)}")
    print(f"Misleading claims violations: {len(misleading_violations)}")
    
    if misleading_violations:
        violation = misleading_violations[0]
        print(f"\n✅ Pattern violation detected:")
        print(f"   Rule: {violation.rule_name}")
        print(f"   Evidence count: {len(violation.evidence)}")
        
        # Check for pattern matches
        pattern_matches = [e for e in violation.evidence if "lose" in e.data.get("matched_term", "").lower()]
        if pattern_matches:
            print(f"   Pattern matches found: {len(pattern_matches)}")
            for evidence in pattern_matches:
                print(f"     - {evidence.data.get('matched_term')} (confidence: {evidence.data.get('confidence')})")
        
        return True
    else:
        print("\n❌ No violation detected")
        return False


def test_multiple_signals_same_violation():
    """Test that multiple signals matching the same rule create one violation with multiple evidence."""
    print("\n" + "=" * 60)
    print("TEST 3: Multiple Signals → One Violation")
    print("=" * 60)
    
    pipeline = CompliancePipeline()
    
    # Create multiple signals that all match the same rule
    signals = [
        create_text_signal("Guaranteed results", "signal1"),
        create_text_signal("Instant delivery", "signal2"),
        create_text_signal("100% safe", "signal3")
    ]
    
    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=b"fake_image",
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    violations = pipeline._check_rules(asset, signals)
    misleading_violations = [v for v in violations if v.rule_id == "misleading_exaggerated_claims"]
    
    print(f"Total violations: {len(violations)}")
    print(f"Misleading claims violations: {len(misleading_violations)}")
    
    if misleading_violations:
        violation = misleading_violations[0]
        print(f"\n✅ Single violation with multiple evidence:")
        print(f"   Violation ID: {violation.violation_id}")
        print(f"   Evidence count: {len(violation.evidence)}")
        print(f"   Expected: 3 (one per signal)")
        
        # Verify all signal IDs are linked
        evidence_signal_ids = [e.signal_id for e in violation.evidence]
        print(f"\n   Linked Signal IDs:")
        for signal_id in evidence_signal_ids:
            print(f"     - {signal_id}")
        
        if len(violation.evidence) == 3:
            print("\n   ✅ Correct: One violation with 3 evidence entries")
            return True
        else:
            print(f"\n   ❌ Incorrect: Expected 3 evidence, got {len(violation.evidence)}")
            return False
    else:
        print("\n❌ No violation detected")
        return False


def test_confidence_scoring():
    """Test that confidence scores are properly assigned."""
    print("\n" + "=" * 60)
    print("TEST 4: Confidence Scoring")
    print("=" * 60)
    
    pipeline = CompliancePipeline()
    
    signals = [
        create_text_signal("Guaranteed instant results")
    ]
    
    asset = Asset(
        image_id=str(uuid.uuid4()),
        image_data=b"fake_image",
        filename="test.jpg",
        content_type="image/jpeg"
    )
    
    violations = pipeline._check_rules(asset, signals)
    misleading_violations = [v for v in violations if v.rule_id == "misleading_exaggerated_claims"]
    
    if misleading_violations:
        violation = misleading_violations[0]
        print(f"✅ Violation detected with confidence scores:")
        
        for evidence in violation.evidence:
            confidence = evidence.data.get("confidence", 0.0)
            signal_conf = evidence.data.get("signal_confidence", 0.0)
            print(f"   Evidence confidence: {confidence:.2f}")
            print(f"   Signal confidence: {signal_conf:.2f}")
            print(f"   Matched term: {evidence.data.get('matched_term')}")
            
            if 0.0 <= confidence <= 1.0:
                print("   ✅ Confidence in valid range (0.0-1.0)")
            else:
                print(f"   ❌ Confidence out of range: {confidence}")
                return False
        
        return True
    else:
        print("❌ No violation detected")
        return False


def main():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("  🧪 Misleading or Exaggerated Claims Rule - Test Suite")
    print("=" * 60)
    
    results = []
    results.append(("Keyword Detection", test_keyword_detection()))
    results.append(("Pattern Detection", test_pattern_detection()))
    results.append(("Multiple Signals → One Violation", test_multiple_signals_same_violation()))
    results.append(("Confidence Scoring", test_confidence_scoring()))
    
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
