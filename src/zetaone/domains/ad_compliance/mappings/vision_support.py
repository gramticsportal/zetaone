"""
Vision → policy evidence mapping.

Vision objects listed here provide SUPPORTING evidence only (not primary triggers).
Used when OCR has already matched; vision objects boost confidence.
"""

VISION_SUPPORT_MAP = {
    "medical_health_claims": {"pill", "medicine", "syringe"},
    "misleading_exaggerated_claims": {"money", "cash", "banknote"},
    "fraud_scams_deceptive": {"money", "cash", "banknote"},
    "financial_products_and_guarantees": {"money", "cash", "banknote"},
    "cryptocurrency_services": {"money", "cash", "banknote"},
}
