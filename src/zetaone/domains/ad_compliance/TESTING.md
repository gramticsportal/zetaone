# Testing the API with Real Images

This guide shows you how to test the compliance API with real image files.

## Quick Start

### 1. Start the API Server

```bash
python app.py
```

You should see:
```
🚀 SentriLens Compliance API
Server starting on http://localhost:5000
```

**Keep this terminal window open!**

### 2. Test with a Real Image

#### Option A: Using the Test Script (Easiest)

```bash
# In a new terminal window
python test_with_real_image.py path/to/your/image.jpg

# With a specific domain
python test_with_real_image.py path/to/your/image.jpg --domain biopharma
```

#### Option B: Using curl

```bash
curl -X POST http://localhost:5000/v1/ads/meta/image/check \
  -F "image=@path/to/your/image.jpg" \
  -F "domain=ads" | jq .
```

#### Option C: Using Python

```python
import requests

with open('your_image.jpg', 'rb') as f:
    response = requests.post(
        'http://localhost:5000/v1/ads/meta/image/check',
        files={'image': f},
        data={'domain': 'ads'}
    )
    
result = response.json()
print(f"Risk Score: {result['risk_score']}")
print(f"Verdict: {result['verdict']}")
print(f"Violations: {len(result['violations'])}")
```

#### Option D: Using the Web App

1. Open `webapp/index.html` in your browser
2. Click or drag-and-drop your image
3. Select a domain
4. Click "Analyze Compliance"
5. View the results

## Supported Image Formats

- JPEG (.jpg, .jpeg)
- PNG (.png)
- GIF (.gif)
- WebP (.webp)
- Any format supported by PIL/Pillow

## Example Test Cases

### Test 1: Image with Misleading Text

Create an image with text like "Guaranteed instant results!" or "100% effective":

```bash
python test_with_real_image.py misleading_ad.jpg --domain ads
```

Expected: Should detect violations for misleading claims.

### Test 2: Clean Image

Test with a simple image (no text):

```bash
python test_with_real_image.py clean_image.jpg
```

Expected: No violations, `likely_approved` verdict.

### Test 3: Medical Claims

Test with medical/health content:

```bash
python test_with_real_image.py medical_ad.jpg --domain biopharma
```

Expected: Should detect prohibited medical claims if present.

## Understanding the Response

The API returns:

```json
{
  "risk_score": 0.85,           // 0.0 (safe) to 1.0 (risky)
  "verdict": "likely_rejected", // likely_approved, borderline, likely_rejected
  "violations": [                // Array of detected violations
    {
      "rule_name": "Misleading or Exaggerated Claims",
      "severity": "HIGH",
      "evidence": [               // Evidence for this violation
        {
          "description": "Misleading claim detected: 'guaranteed'",
          "data": {
            "matched_term": "guaranteed",
            "confidence": 0.95
          }
        }
      ]
    }
  ],
  "fix_suggestions": [           // Actionable suggestions
    "Remove or rephrase misleading claims...",
    "Avoid exaggerated timeframes..."
  ]
}
```

## Troubleshooting

### "Cannot connect to API"

- Make sure `python app.py` is running
- Check the URL is correct: `http://localhost:5000`
- Verify no firewall is blocking port 5000

### "No violations detected"

- The OCR model is currently a placeholder and returns empty signals
- To test violations, you need actual OCR text detection
- For now, violations are only detected if OCR signals are manually injected

### "Invalid image file"

- Make sure the file is a valid image format
- Check the file isn't corrupted
- Try a different image file

## Next Steps

1. **Add Real OCR**: Replace the placeholder OCR model with actual OCR (Tesseract, Google Vision API, etc.)
2. **Test with Various Images**: Try different ad types, domains, and content
3. **Monitor Performance**: Check response times and accuracy
4. **Add More Rules**: Extend the compliance rules for your use case

## Running All Tests

```bash
# Unit tests
python test_outcome.py
python test_rule.py

# API tests (requires running server)
python test_api.py
python test_api_e2e.py

# Test with real image
python test_with_real_image.py your_image.jpg
```
