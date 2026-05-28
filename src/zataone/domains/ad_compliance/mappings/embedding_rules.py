"""
Rule ID → embedding regulation name mapping.

Embedding similarity signals provide low-weight supporting evidence only.
For each rule_id, lists the regulation name(s) from embedding extractor to use.
"""

from __future__ import annotations
EMBEDDING_RULE_MAP = {
    "misleading_exaggerated_claims": "misleading_claims",
    "medical_health_claims": "medical_health_claims",
    "fraud_scams_deceptive": "fraud_scams_deceptive",
    "weapons_ammunition_explosives": "weapons_ammunition_explosives",
    "tobacco_nicotine": "tobacco_nicotine",
    "gambling": "gambling",
    "financial_products_and_guarantees": "financial_products_and_guarantees",
    "cryptocurrency_services": "cryptocurrency_services",
}
