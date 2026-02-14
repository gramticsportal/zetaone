#!/usr/bin/env python3
"""
End-to-end API validation test.
Tests that POST /v1/ads/meta/image/check returns all required fields.
"""

import requests
import json
import time
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import sys
import os

BASE_URL = "http://localhost:5001"

def create_image_with_text(text: str = "Guaranteed instant results!"):
    """Create a test image with text (simulates OCR detection)."""
    # Create image
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use a default font, fallback to basic if not available
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        font = ImageFont.load_default()
    
    # Draw text
    draw.text((10, 80), text, fill='black', font=font)
    
    # Save to bytes
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

def test_v1_check_endpoint_full():
    """Test v1 API endpoint with complete response validation."""
    print("=" * 60)
    print("E2E TEST: POST /v1/ads/meta/image/check")
    print("=" * 60)
    
    try:
        # Create test image with misleading text
        img_bytes = create_image_with_text("Guaranteed 100% effective instant results!")
        
        files = {'image': ('test.png', img_bytes, 'image/png')}
        data = {'domain': 'ads'}
        
        print(f"Making request to {BASE_URL}/v1/ads/meta/image/check...")
        response = requests.post(
            f"{BASE_URL}/v1/ads/meta/image/check",
            files=files,
            data=data,
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Status code {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        result = response.json()
        
        # Validate all required fields
        print("\n" + "-" * 60)
        print("Validating Required Fields:")
        print("-" * 60)
        
        required_fields = {
            "risk_score": {
                "type": (float, int),
                "range": (0.0, 1.0),
                "description": "Risk score (0.0 to 1.0)"
            },
            "verdict": {
                "type": str,
                "values": ["likely_approved", "borderline", "likely_rejected"],
                "description": "Compliance verdict"
            },
            "violations": {
                "type": list,
                "description": "Array of violation objects"
            },
            "fix_suggestions": {
                "type": list,
                "description": "Array of fix suggestion strings"
            }
        }
        
        all_valid = True
        missing_fields = []
        
        for field, validation in required_fields.items():
            if field not in result:
                print(f"  ❌ MISSING: {field}")
                missing_fields.append(field)
                all_valid = False
                continue
            
            value = result[field]
            field_type = validation["type"]
            
            # Type check
            if not isinstance(value, field_type):
                print(f"  ❌ TYPE ERROR: {field} is {type(value).__name__}, expected {field_type.__name__}")
                all_valid = False
                continue
            
            # Range/value checks
            if "range" in validation:
                min_val, max_val = validation["range"]
                if not (min_val <= value <= max_val):
                    print(f"  ❌ RANGE ERROR: {field} = {value}, expected {min_val} to {max_val}")
                    all_valid = False
                    continue
            
            if "values" in validation:
                if value not in validation["values"]:
                    print(f"  ❌ VALUE ERROR: {field} = '{value}', expected one of {validation['values']}")
                    all_valid = False
                    continue
            
            print(f"  ✅ {field}: {value} ({type(value).__name__})")
        
        if missing_fields:
            print(f"\n❌ Missing required fields: {missing_fields}")
            return False
        
        # Validate violations structure
        print("\n" + "-" * 60)
        print("Validating Violations Structure:")
        print("-" * 60)
        
        violations = result.get("violations", [])
        print(f"  Violations count: {len(violations)}")
        
        if violations:
            first_violation = violations[0]
            violation_fields = ["violation_id", "rule_id", "rule_name", "severity", "description", "evidence"]
            
            for field in violation_fields:
                if field not in first_violation:
                    print(f"  ❌ Violation missing field: {field}")
                    all_valid = False
                else:
                    print(f"  ✅ violation.{field}: {type(first_violation[field]).__name__}")
            
            # Validate evidence
            evidence = first_violation.get("evidence", [])
            print(f"  Evidence count: {len(evidence)}")
            
            if evidence:
                first_evidence = evidence[0]
                evidence_fields = ["evidence_id", "evidence_type", "description", "data"]
                
                for field in evidence_fields:
                    if field not in first_evidence:
                        print(f"  ❌ Evidence missing field: {field}")
                        all_valid = False
                    else:
                        print(f"    ✅ evidence.{field}: {type(first_evidence[field]).__name__}")
            else:
                print("  ⚠️  No evidence in violations (may be expected if no signals detected)")
        else:
            print("  ℹ️  No violations detected (may be expected)")
        
        # Validate fix_suggestions
        print("\n" + "-" * 60)
        print("Validating Fix Suggestions:")
        print("-" * 60)
        
        suggestions = result.get("fix_suggestions", [])
        print(f"  Suggestions count: {len(suggestions)}")
        
        if suggestions:
            for i, suggestion in enumerate(suggestions[:3], 1):  # Show first 3
                if not isinstance(suggestion, str):
                    print(f"  ❌ Suggestion {i} is not a string: {type(suggestion).__name__}")
                    all_valid = False
                else:
                    print(f"  ✅ Suggestion {i}: {suggestion[:60]}...")
        else:
            print("  ℹ️  No fix suggestions (expected when no violations)")
        
        # Print full response summary
        print("\n" + "=" * 60)
        print("Response Summary:")
        print("=" * 60)
        print(f"  risk_score: {result.get('risk_score')}")
        print(f"  verdict: {result.get('verdict')}")
        print(f"  violation_count: {len(violations)}")
        print(f"  fix_suggestions_count: {len(suggestions)}")
        print(f"  outcome_id: {result.get('outcome_id', 'N/A')}")
        print(f"  status: {result.get('status', 'N/A')}")
        
        if all_valid:
            print("\n" + "=" * 60)
            print("✅ ALL VALIDATIONS PASSED")
            print("=" * 60)
            print("\nThe API response contains all required fields:")
            print("  ✅ risk_score")
            print("  ✅ verdict")
            print("  ✅ violations (with evidence)")
            print("  ✅ fix_suggestions")
            return True
        else:
            print("\n" + "=" * 60)
            print("❌ VALIDATION FAILED")
            print("=" * 60)
            return False
            
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to API")
        print("Make sure the API is running: python app.py")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run end-to-end validation test."""
    print("\n" + "=" * 60)
    print("  🧪 API End-to-End Validation")
    print("=" * 60)
    print(f"  Testing: {BASE_URL}/v1/ads/meta/image/check")
    print("  Make sure the API is running: python app.py")
    print("=" * 60)
    
    time.sleep(1)
    
    result = test_v1_check_endpoint_full()
    
    if result:
        print("\n🎉 End-to-end validation passed!")
        return 0
    else:
        print("\n⚠️  End-to-end validation failed.")
        return 1

if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print("\n\n👋 Test interrupted")
        exit(1)
