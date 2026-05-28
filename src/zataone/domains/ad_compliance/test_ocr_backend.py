#!/usr/bin/env python3
"""
Test script for OCR backend implementation.
"""

from __future__ import annotations
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

def create_test_image_with_text(text: str = "Guaranteed instant results!"):
    """Create a test image with text."""
    img = Image.new('RGB', (400, 200), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
    except:
        font = ImageFont.load_default()
    
    draw.text((10, 80), text, fill='black', font=font)
    
    img_bytes = BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes.getvalue()

def test_ocr_backend():
    """Test the OCR backend implementation."""
    print("=" * 60)
    print("Testing OCR Backend Implementation")
    print("=" * 60)
    
    try:
        from extractors.ocr_extractor import get_ocr_backend, OCRExtractor, TesseractOCRBackend
        from types import SimpleNamespace

        # Test factory function
        print("\n1. Testing factory function...")
        try:
            backend = get_ocr_backend("tesseract")
            print("   ✅ Factory function works")
        except ImportError as e:
            print(f"   ⚠️  Tesseract not available: {e}")
            print("   Install with: pip install pytesseract")
            print("   Also need: brew install tesseract (Mac) or apt-get install tesseract-ocr (Linux)")
            return False
        except Exception as e:
            print(f"   ❌ Error: {e}")
            return False
        
        # Test backend directly
        print("\n2. Testing TesseractOCRBackend...")
        test_image = create_test_image_with_text("Test OCR 123")
        results = backend.extract_text_data(test_image)
        
        print(f"   Found {len(results)} text detections")
        
        if results:
            print("\n   Sample results:")
            for i, result in enumerate(results[:3], 1):
                print(f"   {i}. Text: '{result['value']}'")
                print(f"      Confidence: {result['confidence']:.2f}")
                print(f"      Bbox: {result['bbox']}")
                print(f"      Type: {result['type']}")
                print(f"      Source: {result['source']}")
        
        # Test OCRExtractor wrapper
        print("\n3. Testing OCRExtractor wrapper...")
        ocr_extractor = OCRExtractor()
        asset = SimpleNamespace(image_data=test_image)
        signals = ocr_extractor.extract(asset)
        
        print(f"   Generated {len(signals)} Signal objects")
        
        if signals:
            print("\n   Sample Signal:")
            signal = signals[0]
            print(f"   - Signal ID: {signal.signal_id}")
            print(f"   - Type: {signal.signal_type}")
            print(f"   - Source: {signal.source_model}")
            print(f"   - Confidence: {signal.confidence:.2f}")
            print(f"   - Text: {signal.raw_data.get('text', 'N/A')}")
            print(f"   - Bbox: {signal.bounding_box}")
        
        print("\n" + "=" * 60)
        print("✅ OCR Backend Test Complete")
        print("=" * 60)
        return True
        
    except ImportError as e:
        print(f"\n❌ Import Error: {e}")
        print("\nInstall dependencies:")
        print("  pip install pytesseract pillow")
        print("\nInstall Tesseract:")
        print("  Mac: brew install tesseract")
        print("  Linux: apt-get install tesseract-ocr")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_ocr_backend()
    sys.exit(0 if success else 1)
