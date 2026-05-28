#!/usr/bin/env python3
"""
Test the API with a real image file.

Usage:
    python test_with_real_image.py path/to/your/image.jpg
    python test_with_real_image.py path/to/your/image.jpg --domain biopharma
"""

from __future__ import annotations
import sys
import requests
import json
import argparse

BASE_URL = "http://localhost:5001"


def test_with_image(image_path: str, domain: str = "ads"):
    """Test the API with a real image file."""
    
    print("=" * 60)
    print("Testing API with Real Image")
    print("=" * 60)
    print(f"Image: {image_path}")
    print(f"Domain: {domain}")
    print(f"Endpoint: {BASE_URL}/v1/ads/meta/image/check")
    print()
    
    try:
        # Open and read the image file
        with open(image_path, 'rb') as f:
            files = {'image': (image_path, f, 'image/jpeg')}
            data = {'domain': domain}
            
            print("Sending request...")
            response = requests.post(
                f"{BASE_URL}/v1/ads/meta/image/check",
                files=files,
                data=data,
                timeout=30
            )
        
        print(f"Status Code: {response.status_code}\n")
        
        if response.status_code != 200:
            print(f"❌ Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
        
        result = response.json()
        
        # Print results
        print("=" * 60)
        print("COMPLIANCE RESULTS")
        print("=" * 60)
        print(f"Risk Score: {result.get('risk_score', 'N/A')}")
        print(f"Risk Level: {result.get('risk_level', 'N/A')}")
        print(f"Verdict: {result.get('verdict', 'N/A')}")
        print(f"Status: {result.get('status', 'N/A')}")
        print()
        
        violations = result.get('violations', [])
        print(f"Violations Found: {len(violations)}")
        
        if violations:
            print("\n" + "-" * 60)
            print("VIOLATIONS:")
            print("-" * 60)
            for i, violation in enumerate(violations, 1):
                print(f"\n{i}. {violation.get('rule_name', 'Unknown Rule')}")
                print(f"   Severity: {violation.get('severity', 'N/A')}")
                print(f"   Description: {violation.get('description', 'N/A')}")
                
                evidence = violation.get('evidence', [])
                if evidence:
                    print(f"   Evidence ({len(evidence)} items):")
                    for j, ev in enumerate(evidence, 1):
                        print(f"     {j}. {ev.get('description', 'N/A')}")
                        if 'data' in ev and 'matched_term' in ev['data']:
                            print(f"        Matched: '{ev['data']['matched_term']}'")
        else:
            print("\n✅ No violations detected!")
        
        suggestions = result.get('fix_suggestions', [])
        if suggestions:
            print("\n" + "-" * 60)
            print("FIX SUGGESTIONS:")
            print("-" * 60)
            for i, suggestion in enumerate(suggestions, 1):
                print(f"{i}. {suggestion}")
        
        print("\n" + "=" * 60)
        print("✅ Test completed successfully!")
        print("=" * 60)
        
        return True
        
    except FileNotFoundError:
        print(f"❌ Error: Image file not found: {image_path}")
        return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Error: Cannot connect to API at {BASE_URL}")
        print("Make sure the API is running: python app.py")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Test the compliance API with a real image file'
    )
    parser.add_argument(
        'image_path',
        help='Path to the image file to test'
    )
    parser.add_argument(
        '--domain',
        choices=['ads', 'biopharma', 'finance'],
        default='ads',
        help='Domain for compliance checking (default: ads)'
    )
    
    args = parser.parse_args()
    
    success = test_with_image(args.image_path, args.domain)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
