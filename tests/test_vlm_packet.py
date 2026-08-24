"""Structured VLM packet parse → matcher signals → document text."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))


def test_parse_and_normalize_fenced_json():
    from zataone.document.vlm_packet import (
        normalize_vlm_structured,
        parse_vlm_json,
        structured_to_matcher_signals,
    )

    raw = """```json
    {
      "is_advertisement": true,
      "ocr_text": "Lose 20 lbs in 7 days GUARANTEED",
      "ad_claims_text": "Lose 20 lbs in 7 days GUARANTEED. Order now!",
      "objects": [{"label": "pill bottle", "confidence": 0.8, "bbox": [10, 20, 50, 60]}],
      "scene_description": "Product ad with smiling person",
      "notes": ""
    }
    ```"""
    parsed = parse_vlm_json(raw)
    assert parsed is not None
    st = normalize_vlm_structured(parsed)
    assert "GUARANTEED" in st["ad_claims_text"]
    assert st["objects"][0]["label"] == "pill bottle"
    sigs = structured_to_matcher_signals(st)
    types = {s.raw_data["type"] for s in sigs}
    assert "ocr_text" in types
    assert "vlm_claims_text" in types
    assert "vision_object" in types
    # scene must NOT become a matcher signal
    assert all(s.raw_data.get("type") != "scene_description" for s in sigs)


def test_document_builder_puts_claims_before_scenes():
    from zataone.document.builder import DocumentBuilder
    from zataone.document.vlm_packet import normalize_vlm_structured, structured_to_matcher_signals

    st = normalize_vlm_structured(
        {
            "ocr_text": "Headline text",
            "ad_claims_text": "Miracle cure guaranteed",
            "objects": [{"label": "cigarette", "confidence": 0.9}],
            "scene_description": "Should not dominate matcher text alone",
        }
    )
    asset = SimpleNamespace(type="image", content=None, id=None)
    doc = DocumentBuilder.build(asset, structured_to_matcher_signals(st))
    assert "Miracle cure guaranteed" in doc.normalized_text
    assert "Ad claims:" in doc.normalized_text
    assert "cigarette" in doc.normalized_text
    # scene_description is LLM-only — not injected as free prose
    assert "Should not dominate" not in doc.normalized_text


def test_ocr_vision_flags_default_off(monkeypatch):
    monkeypatch.delenv("ZATAONE_ENABLE_OCR", raising=False)
    monkeypatch.delenv("ZATAONE_ENABLE_VISION", raising=False)
    from zataone.core.extractor_flags import ocr_enabled, vision_dino_enabled, vlm_primary_image_path

    assert ocr_enabled() is False
    assert vision_dino_enabled() is False
    assert vlm_primary_image_path() is True
