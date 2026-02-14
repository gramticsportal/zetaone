"""
VLM (Vision Language Model) extractor - contextual image analysis.

Uses GPT-4o Vision API for borderline case reasoning.
Inherits from zetaone.extractors.base.BaseExtractor.
"""

from typing import List, Dict, Any
import sys
import os
import base64
import json

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

_zetaone_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_src_root = os.path.dirname(_zetaone_dir)
if os.path.exists(os.path.join(_zetaone_dir, "extractors", "base.py")):
    if _src_root not in sys.path:
        sys.path.insert(0, _src_root)

try:
    from zetaone.extractors.base import BaseExtractor
except ImportError:
    from abc import ABC, abstractmethod
    class BaseExtractor(ABC):
        extractor_id: str = ""
        version: str = ""
        @abstractmethod
        def extract(self, asset): pass

try:
    import requests
except ImportError:
    requests = None


def analyze_image_context(
    image_bytes: bytes,
    ocr_texts: List[str],
    vision_objects: List[Dict[str, Any]],
    policy_id: str,
) -> str:
    """
    Returns a short natural-language explanation (<= 3 sentences).
    Uses GPT-4o Vision API. Reads VLM_API_KEY from environment.
    """
    api_key = os.environ.get("VLM_API_KEY")
    if not api_key:
        raise RuntimeError("VLM_API_KEY is not set")
    if requests is None:
        raise ImportError("requests is required for VLM API calls")

    ocr_texts_clean = [t.strip() for t in (ocr_texts or []) if t and t.strip()][:25]
    objs = []
    for obj in vision_objects or []:
        label = str(obj.get("label", "")).strip()
        if not label:
            continue
        objs.append({"label": label, "confidence": obj.get("confidence")})
    objs = objs[:25]
    policy_name = policy_id.replace("_", " ").strip()

    prompt = (
        "You are helping explain compliance evidence for an ad image.\n"
        "Be factual and neutral. Do NOT give a verdict, policy decision, or score.\n"
        "Respond with at most 3 sentences.\n\n"
        f"Policy: {policy_name}\n"
        f"OCR text snippets: {ocr_texts_clean}\n"
        f"Vision objects: {objs}\n\n"
        "Task: Briefly explain whether the image content and text supports the policy concern, "
        "and note any ambiguity (e.g., medical vs non-medical usage) if relevant."
    )

    b64 = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64}"
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        "max_tokens": 120,
        "temperature": 0.2,
    }

    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    resp.raise_for_status()
    out = resp.json()
    text = (out.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not isinstance(text, str):
        text = str(text)
    return text.strip()[:600]


class VLMExtractor(BaseExtractor):
    """VLM extractor for contextual analysis (borderline cases)."""

    extractor_id = "ad_compliance_vlm"
    version = "1.0.0"

    def __init__(self):
        self.model_name = "gpt_4o_vision_api"

    def extract(self, asset: Any) -> List:
        """
        Base extract returns empty - VLM is used for borderline context only.
        Call analyze_image_context() for borderline case reasoning.
        """
        return []

    def analyze_image_context(
        self,
        image_bytes: bytes,
        ocr_texts: List[str],
        vision_objects: List[Dict[str, Any]],
        policy_id: str,
    ) -> str:
        """Analyze image context for borderline compliance cases."""
        return analyze_image_context(image_bytes, ocr_texts, vision_objects, policy_id)
