# Structured Gemini VLM packet → matcher signals + LLM-facing summary

from __future__ import annotations

import json
import logging
import re
import uuid
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)

VLM_PACKET_VERSION = "vlm_packet_v1"


def parse_vlm_json(raw: str | None) -> dict[str, Any] | None:
    """Extract JSON object from model text (raw or fenced)."""
    if not raw or not str(raw).strip():
        return None
    text = str(raw).strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, flags=re.IGNORECASE)
    if fence:
        text = fence.group(1).strip()
    # First {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        logger.info("vlm_packet: JSON parse failed")
        return None
    return obj if isinstance(obj, dict) else None


def normalize_vlm_structured(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize model JSON into a stable schema."""
    d = raw or {}
    objects_in = d.get("objects") or []
    objects: list[dict[str, Any]] = []
    if isinstance(objects_in, list):
        for item in objects_in[:40]:
            if isinstance(item, str):
                label = item.strip()
                if label:
                    objects.append({"label": label.lower(), "confidence": 0.7, "bbox": None})
                continue
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("name") or "").strip().lower()
            if not label:
                continue
            conf = item.get("confidence", item.get("score", 0.7))
            try:
                conf_f = float(conf)
            except (TypeError, ValueError):
                conf_f = 0.7
            bbox = item.get("bbox") or item.get("box")
            objects.append({"label": label, "confidence": conf_f, "bbox": bbox})

    def _s(key: str, *alts: str) -> str:
        for k in (key, *alts):
            v = d.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        return ""

    is_ad = d.get("is_advertisement")
    if isinstance(is_ad, str):
        is_ad = is_ad.strip().lower() in ("1", "true", "yes")
    elif is_ad is not None:
        is_ad = bool(is_ad)

    return {
        "schema": VLM_PACKET_VERSION,
        "is_advertisement": is_ad,
        "ocr_text": _s("ocr_text", "visible_text", "text"),
        "ad_claims_text": _s("ad_claims_text", "claims_text", "ad_copy"),
        "objects": objects,
        "scene_description": _s("scene_description", "description", "scene"),
        "notes": _s("notes", "uncertainty", "illegible_notes"),
    }


def inspection_summary_for_llm(structured: dict[str, Any]) -> str:
    """Human-readable summary for final LLM (full context)."""
    parts: list[str] = []
    if structured.get("is_advertisement") is False:
        parts.append("Likely not an advertisement.")
    elif structured.get("is_advertisement") is True:
        parts.append("Appears to be an advertisement or promotional creative.")
    if structured.get("scene_description"):
        parts.append("Scene: " + structured["scene_description"])
    if structured.get("ocr_text"):
        parts.append("Visible text (OCR):\n" + structured["ocr_text"][:6000])
    if structured.get("ad_claims_text"):
        parts.append("Ad claims / CTAs:\n" + structured["ad_claims_text"][:4000])
    objs = structured.get("objects") or []
    if objs:
        labels = ", ".join(
            f"{o['label']} ({o.get('confidence', 0):.2f})" for o in objs[:30] if o.get("label")
        )
        if labels:
            parts.append("Objects: " + labels)
    if structured.get("notes"):
        parts.append("Notes: " + structured["notes"][:1000])
    return "\n\n".join(parts).strip()


def structured_to_matcher_signals(structured: dict[str, Any] | None) -> list[Any]:
    """
    Convert VLM packet into duck-typed signals for DocumentBuilder + hybrid.

    Matcher-facing only: OCR text, ad claims, objects.
    Scene description is intentionally omitted (LLM-only via advisory_vlm).
    """
    if not structured:
        return []
    signals: list[Any] = []

    ocr = (structured.get("ocr_text") or "").strip()
    if ocr:
        signals.append(
            SimpleNamespace(
                signal_id=str(uuid.uuid4()),
                signal_type="text",
                extractor_id="gemini_vlm",
                source_model="gemini_vlm",
                confidence=0.85,
                raw_data={
                    "text": ocr[:20000],
                    "type": "ocr_text",
                    "source": "image",
                    "model": "gemini_vlm",
                    "bbox": None,
                },
                value=None,
            )
        )

    claims = (structured.get("ad_claims_text") or "").strip()
    if claims:
        signals.append(
            SimpleNamespace(
                signal_id=str(uuid.uuid4()),
                signal_type="text",
                extractor_id="gemini_vlm",
                source_model="gemini_vlm",
                confidence=0.85,
                raw_data={
                    "text": claims[:12000],
                    "type": "vlm_claims_text",
                    "source": "image",
                    "model": "gemini_vlm",
                },
                value=None,
            )
        )

    for obj in structured.get("objects") or []:
        label = str(obj.get("label") or "").strip().lower()
        if not label:
            continue
        conf = float(obj.get("confidence") or 0.7)
        bbox = obj.get("bbox")
        bbox_list = None
        bounding_box = None
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
            bbox_list = [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])]
            # accept [x,y,w,h] or [x0,y0,x1,y1] — store as xywh when w/h look like extents
            x0, y0, a, b = bbox_list
            if a > x0 and b > y0 and a <= 2 and b <= 2:
                # normalized x1,y1
                w, h = a - x0, b - y0
            elif a >= x0 and b >= y0 and (a > 10 or b > 10):
                # likely x1,y1 in pixels
                w, h = max(0.0, a - x0), max(0.0, b - y0)
            else:
                w, h = a, b
            bounding_box = {"x": x0, "y": y0, "width": w, "height": h}
            bbox_list = [x0, y0, w, h]
        signals.append(
            SimpleNamespace(
                signal_id=str(uuid.uuid4()),
                signal_type="object",
                extractor_id="gemini_vlm",
                source_model="gemini_vlm",
                confidence=conf,
                raw_data={
                    "type": "vision_object",
                    "label": label,
                    "confidence": conf,
                    "bbox": bbox_list,
                    "source": "image",
                    "model": "gemini_vlm",
                },
                bounding_box=bounding_box,
                value=None,
            )
        )

    return signals
