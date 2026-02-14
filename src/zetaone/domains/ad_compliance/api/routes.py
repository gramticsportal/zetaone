"""
API route handlers.
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from datetime import datetime
import uuid
import base64
from io import BytesIO
from PIL import Image

import sys
import os

# Add parent directory to path for imports
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from schemas.models import Asset
from pipeline.engine import CompliancePipeline


def create_app() -> Flask:
    """Create and configure Flask app."""
    app = Flask(__name__)
    CORS(app)
    
    pipeline = CompliancePipeline()
    
    @app.route('/', methods=['GET'])
    def home():
        """API information endpoint."""
        return jsonify({
            "app": "SentriLens Compliance API",
            "version": "1.0.0",
            "description": "API-first advertising compliance system for Meta image ads",
            "endpoints": {
                "health": "/health",
                "check": "/v1/ads/meta/image/check (POST)",
                "analyze": "/analyze (POST) - legacy",
                "rules": "/rules",
                "viewer": "/viewer"
            }
        })
    
    @app.route('/health', methods=['GET'])
    def health():
        """Health check endpoint."""
        return jsonify({
            "status": "ok",
            "timestamp": datetime.now().isoformat()
        })
    
    @app.route('/v1/ads/meta/image/check', methods=['POST'])
    def check_image():
        """
        Check image for Meta advertising compliance (v1 API contract).
        
        Request:
            - Multipart form with 'image' file
            - Optional 'domain' field (biopharma, finance, ads)
        
        Response:
            - risk_score: float (0.0 to 1.0)
            - verdict: string (likely_approved, borderline, likely_rejected)
            - violations: array of violation objects
            - evidence: nested within violations
            - fix_suggestions: array of strings
        """
        try:
            # Check if image is provided
            if 'image' not in request.files:
                return jsonify({
                    "error": "Validation error",
                    "message": "No image file provided"
                }), 400
            
            image_file = request.files['image']
            if image_file.filename == '':
                return jsonify({
                    "error": "Validation error",
                    "message": "Empty file provided"
                }), 400
            
            # Read image data
            image_data = image_file.read()
            
            # Validate it's an image
            try:
                Image.open(BytesIO(image_data))
            except Exception:
                return jsonify({
                    "error": "Validation error",
                    "message": "Invalid image file"
                }), 400
            
            # Get optional domain
            domain = request.form.get('domain', 'ads').lower()
            
            # Create asset
            asset = Asset(
                image_id=str(uuid.uuid4()),
                image_data=image_data,
                filename=image_file.filename,
                content_type=image_file.content_type or 'image/jpeg',
                metadata={"domain": domain}
            )
            
            # Process through pipeline
            outcome = pipeline.process(asset)
            
            # Convert outcome to JSON response
            return jsonify(_outcome_to_dict(outcome)), 200
            
        except Exception as e:
            return jsonify({
                "error": "Internal server error",
                "message": str(e)
            }), 500
    
    @app.route('/analyze', methods=['POST'])
    def analyze():
        """
        Analyze image for compliance violations (legacy endpoint).
        
        Request:
            - Multipart form with 'image' file
            - Optional 'domain' field (biopharma, finance, ads)
        
        Response:
            - Outcome with violations, risk score, status
        """
        # Delegate to check_image for consistency
        return check_image()
    
    @app.route('/viewer')
    @app.route('/viewer/')
    def viewer():
        """Serve the viewer-only web app (static)."""
        webapp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'webapp')
        return send_from_directory(webapp_dir, 'index.html')

    @app.route('/rules', methods=['GET'])
    def get_rules():
        """Get available compliance rules."""
        # Access rules from pipeline (create temporary instance to access rules)
        temp_pipeline = CompliancePipeline()
        rules = temp_pipeline._load_rules()
        
        rules_summary = {}
        for rule_id, rule in rules.items():
            rules_summary[rule_id] = {
                "name": rule["name"],
                "severity": rule["severity"],
                "description": rule["description"]
            }
        
        return jsonify({
            "rules": rules_summary,
            "total_rules": len(rules)
        })
    
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({
            "error": "Not found",
            "message": "Endpoint not found"
        }), 404
    
    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500
    
    return app


def _outcome_to_dict(outcome):
    """Convert Outcome to JSON-serializable dict."""
    return {
        "outcome_id": outcome.outcome_id,
        "asset_id": outcome.asset_id,
        "status": outcome.status.value,
        "risk_score": round(outcome.risk_score, 2),
        "risk_level": _risk_score_to_level(outcome.risk_score),
        "verdict": outcome.verdict.value,
        "violations": [_violation_to_dict(v) for v in outcome.violations],
        "violation_count": len(outcome.violations),
        "signals_count": len(outcome.signals),
        "fix_suggestions": outcome.fix_suggestions,
        "processed_at": outcome.processed_at.isoformat(),
        "metadata": outcome.metadata
    }


def _violation_to_dict(violation):
    """Convert Violation to JSON-serializable dict."""
    return {
        "violation_id": violation.violation_id,
        "rule_id": violation.rule_id,
        "rule_name": violation.rule_name,
        "severity": violation.severity.value,
        "description": violation.description,
        "evidence": [_evidence_to_dict(e) for e in violation.evidence],
        "detected_at": violation.detected_at.isoformat()
    }


def _evidence_to_dict(evidence):
    """Convert Evidence to JSON-serializable dict."""
    return {
        "evidence_id": evidence.evidence_id,
        "evidence_type": evidence.evidence_type,
        "description": evidence.description,
        "data": evidence.data
    }


def _risk_score_to_level(score: float) -> str:
    """Convert risk score to level."""
    if score < 0.3:
        return "LOW"
    elif score < 0.6:
        return "MEDIUM"
    elif score < 0.85:
        return "HIGH"
    else:
        return "CRITICAL"
