#!/usr/bin/env python3
"""
Test script for Zataone Ad Compliance API (domain bundle)
Run this to test all endpoints
"""

import requests
import json
import time
from io import BytesIO
from PIL import Image

BASE_URL = "http://localhost:5001"

def print_section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def test_health():
    """Test health endpoint"""
    print_section("TEST 1: Health Check")
    
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ PASSED")
            return True
        else:
            print("❌ FAILED")
            return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_info():
    """Test API info endpoint"""
    print_section("TEST 2: API Info")
    
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"App: {data.get('app')}")
        print(f"Version: {data.get('version')}")
        
        if response.status_code == 200:
            print("✅ PASSED")
            return True
        else:
            print("❌ FAILED")
            return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def create_test_image():
    """Create a simple test image"""
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

def test_analyze_image():
    """Test image analysis endpoint (legacy)"""
    print_section("TEST 3: Analyze Image (Legacy)")
    
    try:
        # Create test image
        img_bytes = create_test_image()
        
        files = {'image': ('test.png', img_bytes, 'image/png')}
        data = {'domain': 'biopharma'}
        
        response = requests.post(
            f"{BASE_URL}/analyze",
            files=files,
            data=data
        )
        
        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Status: {result.get('status')}")
        print(f"Risk Score: {result.get('risk_score')}")
        print(f"Risk Level: {result.get('risk_level')}")
        print(f"Violations: {result.get('violation_count')}")
        
        if response.status_code == 200:
            print("✅ PASSED")
            return True
        else:
            print("❌ FAILED")
            return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_v1_check_endpoint():
    """Test v1 API endpoint with full compliance response validation"""
    print_section("TEST 3b: POST /v1/ads/meta/image/check - Full Response")
    
    try:
        # Create test image
        img_bytes = create_test_image()
        
        files = {'image': ('test.png', img_bytes, 'image/png')}
        data = {'domain': 'ads'}
        
        response = requests.post(
            f"{BASE_URL}/v1/ads/meta/image/check",
            files=files,
            data=data
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"❌ FAILED: Status code {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        result = response.json()
        
        # Validate required fields
        required_fields = {
            "risk_score": (float, "Risk score must be a float"),
            "verdict": (str, "Verdict must be a string"),
            "violations": (list, "Violations must be a list"),
            "fix_suggestions": (list, "Fix suggestions must be a list")
        }
        
        print("\nValidating response structure:")
        all_valid = True
        
        for field, (field_type, error_msg) in required_fields.items():
            if field not in result:
                print(f"  ❌ Missing required field: {field}")
                all_valid = False
            elif not isinstance(result[field], field_type):
                print(f"  ❌ {error_msg}")
                all_valid = False
            else:
                print(f"  ✅ {field}: {type(result[field]).__name__}")
        
        # Validate risk_score range
        if "risk_score" in result:
            risk_score = result["risk_score"]
            if not (0.0 <= risk_score <= 1.0):
                print(f"  ❌ risk_score out of range: {risk_score} (expected 0.0-1.0)")
                all_valid = False
            else:
                print(f"  ✅ risk_score value: {risk_score:.2f}")
        
        # Validate verdict values
        if "verdict" in result:
            valid_verdicts = ["likely_approved", "borderline", "likely_rejected"]
            verdict = result["verdict"]
            if verdict not in valid_verdicts:
                print(f"  ❌ Invalid verdict: {verdict} (expected one of {valid_verdicts})")
                all_valid = False
            else:
                print(f"  ✅ verdict: {verdict}")
        
        # Validate violations structure
        if "violations" in result:
            violations = result["violations"]
            print(f"  ✅ violations count: {len(violations)}")
            
            # Check that violations contain evidence
            if violations:
                first_violation = violations[0]
                if "evidence" not in first_violation:
                    print(f"  ❌ Violations missing 'evidence' field")
                    all_valid = False
                else:
                    evidence = first_violation["evidence"]
                    print(f"  ✅ First violation has {len(evidence)} evidence entries")
                    if evidence:
                        # Validate evidence structure
                        first_evidence = evidence[0]
                        evidence_fields = ["evidence_id", "evidence_type", "description", "data"]
                        for field in evidence_fields:
                            if field not in first_evidence:
                                print(f"  ❌ Evidence missing field: {field}")
                                all_valid = False
                            else:
                                print(f"    ✅ evidence.{field}: {type(first_evidence[field]).__name__}")
        
        # Validate fix_suggestions
        if "fix_suggestions" in result:
            suggestions = result["fix_suggestions"]
            print(f"  ✅ fix_suggestions count: {len(suggestions)}")
            if suggestions:
                print(f"    Example: {suggestions[0][:60]}...")
        
        # Print summary
        print(f"\nResponse Summary:")
        print(f"  risk_score: {result.get('risk_score', 'N/A')}")
        print(f"  verdict: {result.get('verdict', 'N/A')}")
        print(f"  violations: {len(result.get('violations', []))}")
        print(f"  fix_suggestions: {len(result.get('fix_suggestions', []))}")
        
        if all_valid:
            print("\n✅ PASSED - All required fields present and valid")
            return True
        else:
            print("\n❌ FAILED - Some validation checks failed")
            return False
            
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_rules():
    """Test rules endpoint"""
    print_section("TEST 4: Get Rules")
    
    try:
        response = requests.get(f"{BASE_URL}/rules")
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Total Rules: {data.get('total_rules')}")
        
        if response.status_code == 200:
            print("✅ PASSED")
            return True
        else:
            print("❌ FAILED")
            return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def test_error_handling():
    """Test error handling"""
    print_section("TEST 5: Error Handling (No Image)")
    
    try:
        response = requests.post(
            f"{BASE_URL}/analyze",
            data={'domain': 'biopharma'}
        )
        
        print(f"Status Code: {response.status_code}")
        result = response.json()
        print(f"Error: {result.get('error')}")
        
        if response.status_code == 400:
            print("✅ PASSED (Correctly rejected missing image)")
            return True
        else:
            print("❌ FAILED")
            return False
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  🧪 Zataone Ad Compliance API — test suite")
    print("="*60)
    print(f"  Testing: {BASE_URL}")
    print("  Make sure the API is running: python app.py")
    print("="*60)
    
    time.sleep(1)
    
    results = []
    results.append(("Health Check", test_health()))
    results.append(("API Info", test_info()))
    results.append(("Analyze Image (Legacy)", test_analyze_image()))
    results.append(("V1 Check Endpoint - Full Response", test_v1_check_endpoint()))
    results.append(("List Rules", test_rules()))
    results.append(("Error Handling", test_error_handling()))
    
    print_section("TEST SUMMARY")
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
        print("\n⚠️  Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    try:
        exit(main())
    except KeyboardInterrupt:
        print("\n\n👋 Tests interrupted")
        exit(1)
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to API")
        print("Make sure the API is running: python app.py")
        exit(1)
