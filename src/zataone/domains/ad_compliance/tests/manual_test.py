#!/usr/bin/env python3
"""
Production-style manual test for Docker + Cloud Run readiness.

Sends a real image to POST /v1/ads/meta/image/check, prints full JSON,
and verifies OCR, rules, vision/embeddings, and VLM gating.

Usage:
    python tests/manual_test.py [image_path]
    python tests/manual_test.py tests/assets/fixture_with_text.png

Default image: tests/assets/fixture_with_text.png (contains "guaranteed!" -
triggers misleading + medical policy violations).

Prerequisite: API running on http://localhost:5001
"""

from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌ Requires: pip install requests")
    sys.exit(1)

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:5001")
DEFAULT_IMAGE = "tests/assets/fixture_with_text.png"


def _resolve_image_path(path: str) -> Path:
    """Resolve path relative to project root."""
    root = Path(__file__).resolve().parent.parent
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    return p


def run_manual_test(image_path: str) -> dict:
    """
    Send image to API, return parsed response and verification results.
    """
    resolved = _resolve_image_path(image_path)
    if not resolved.exists():
        return {
            "ok": False,
            "error": f"Image not found: {resolved}",
            "response": None,
            "elapsed_ms": 0,
        }

    # Infer content type
    ext = resolved.suffix.lower()
    ct = "image/png" if ext == ".png" else "image/jpeg"

    url = f"{BASE_URL}/v1/ads/meta/image/check"
    files = {"image": (resolved.name, open(resolved, "rb"), ct)}
    data = {"domain": "ads"}

    start = time.perf_counter()
    try:
        resp = requests.post(url, files=files, data=data, timeout=120)
    except requests.exceptions.ConnectionError:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "ok": False,
            "error": f"Cannot connect to {BASE_URL}. Start API: python app.py",
            "response": None,
            "elapsed_ms": elapsed_ms,
        }
    finally:
        files["image"][1].close()

    elapsed_ms = (time.perf_counter() - start) * 1000

    if resp.status_code != 200:
        try:
            body = resp.json()
        except Exception:
            body = {"raw": resp.text}
        return {
            "ok": False,
            "error": f"HTTP {resp.status_code}",
            "response": body,
            "elapsed_ms": elapsed_ms,
        }

    try:
        result = resp.json()
    except Exception as e:
        return {
            "ok": False,
            "error": f"Invalid JSON: {e}",
            "response": None,
            "elapsed_ms": elapsed_ms,
        }

    # Verifications
    violations = result.get("violations", [])
    metadata = result.get("metadata", {})

    has_text_match = False
    has_vision = False
    has_embedding = False
    has_vlm = False
    routing = metadata.get("routing")
    verdict = result.get("verdict", "")
    risk_score = result.get("risk_score", 0.0)

    for v in violations:
        for ev in v.get("evidence", []):
            et = ev.get("evidence_type", "")
            if et == "text_match":
                has_text_match = True
            elif et == "vision_object":
                has_vision = True
            elif et == "image_embedding_similarity":
                has_embedding = True
            elif et == "vlm_reasoning_stub":
                has_vlm = True

    # VLM should only appear when: routing=borderline AND risk<0.7
    vlm_ok = True
    if has_vlm:
        if routing != "borderline_requires_context":
            vlm_ok = False
        elif verdict == "likely_rejected" or risk_score >= 0.7:
            vlm_ok = False

    return {
        "ok": True,
        "response": result,
        "elapsed_ms": elapsed_ms,
        "verifications": {
            "ocr_fired": has_text_match,
            "rules_triggered": len(violations) >= 1,
            "vision_supporting": has_vision,
            "embedding_supporting": has_embedding,
            "vlm_gating_ok": vlm_ok,
            "vlm_present": has_vlm,
        },
    }


def main():
    image_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE

    print("=" * 60)
    print("Production-style manual test (Docker / Cloud Run readiness)")
    print("=" * 60)
    print(f"Image: {image_path}")
    print(f"Endpoint: {BASE_URL}/v1/ads/meta/image/check")
    print()

    out = run_manual_test(image_path)

    if out.get("error"):
        print(f"❌ {out['error']}")
        if out.get("response"):
            print(json.dumps(out["response"], indent=2))
        sys.exit(1)

    result = out["response"]
    ver = out["verifications"]
    elapsed = out["elapsed_ms"]

    # Print full JSON
    print("FULL JSON RESPONSE:")
    print("-" * 60)
    print(json.dumps(result, indent=2))
    print("-" * 60)
    print(f"Elapsed: {elapsed:.0f} ms")
    print()

    # Verification summary
    print("VERIFICATIONS:")
    print("-" * 60)
    print(f"  OCR fired:              {'✅' if ver['ocr_fired'] else '❌'}")
    print(f"  Rules triggered:        {'✅' if ver['rules_triggered'] else '❌'}")
    print(f"  Vision (supporting):    {'✅ present' if ver['vision_supporting'] else '○ absent (may be expected)'}")
    print(f"  Embedding (supporting): {'✅ present' if ver['embedding_supporting'] else '○ absent (may be expected)'}")
    print(f"  VLM gating OK:          {'✅' if ver['vlm_gating_ok'] else '❌ (VLM evidence when should not)'}")
    print(f"  VLM present:            {'yes' if ver['vlm_present'] else 'no (only for borderline, risk<0.7)'}")
    print("-" * 60)

    all_critical = ver["ocr_fired"] and ver["rules_triggered"] and ver["vlm_gating_ok"]
    if not all_critical:
        print("\n❌ READINESS: Fix critical checks first (OCR, rules, VLM gating)")
        sys.exit(1)

    # Docker-related flags
    print("\nDOCKER / CLOUD RUN FLAGS:")
    print("-" * 60)
    if elapsed > 30000:
        print(f"  ⚠ Model load (cold start): ~{elapsed/1000:.1f}s — consider health-check warm-up")
    if elapsed > 10000:
        print(f"  ⚠ Request latency: {elapsed/1000:.1f}s — SigLIP + Grounding DINO + OCR on CPU")
    print("  ⚠ Memory: SigLIP (~400MB) + Grounding DINO (~500MB) + torch — recommend ≥2GB container")
    print("  ⚠ transformers>=4.50.0 required (Grounding DINO CONFIG_MAPPING)")
    print("-" * 60)

    print("\n✅ READINESS: Docker-ready (run with sufficient memory and warm-up)")
    sys.exit(0)


if __name__ == "__main__":
    main()
