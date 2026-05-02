"""
Main application entry point.

Run with: python app.py
Gunicorn: gunicorn app:app
"""

from api.routes import create_app

app = create_app()

if __name__ == '__main__':
    
    print("=" * 60)
    print("🚀 Zataone Ad Compliance API")
    print("=" * 60)
    print("Server starting on http://localhost:5001")
    print()
    print("Endpoints:")
    print("  GET  /                        - API info")
    print("  GET  /health                   - Health check")
    print("  POST /v1/ads/meta/image/check - Check image compliance (v1 API)")
    print("  POST /analyze                 - Analyze image (legacy)")
    print("  GET  /rules                   - List rules")
    print()
    print("Example (v1 API):")
    print("  curl -X POST http://localhost:5001/v1/ads/meta/image/check \\")
    print("    -F 'image=@your_image.jpg' \\")
    print("    -F 'domain=ads'")
    print()
    print("Example (legacy):")
    print("  curl -X POST http://localhost:5001/analyze \\")
    print("    -F 'image=@your_image.jpg' \\")
    print("    -F 'domain=biopharma'")
    print("=" * 60)
    
    app.run(debug=True, host='0.0.0.0', port=5001)
