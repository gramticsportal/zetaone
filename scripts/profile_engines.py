#!/usr/bin/env python3
"""
Profile legacy PolicyEngine vs Phase B HybridEngine locally (no Cloud Run).

Usage (from repo root):
  python scripts/profile_engines.py
  python scripts/profile_engines.py --image /path/to/ad.png
  python scripts/profile_engines.py --nlp-backend bow
  python scripts/profile_engines.py --nlp-backend minilm --warmup

Notes:
  - Image slowness on Cloud Run is usually OCR + DINO load + Gemini VLM/LLM,
    not the rule engine. This script separates those stages.
  - MiniLM first load may download once into HF cache; --warmup times that separately.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


SAMPLES = [
    (
        "exaggerated_health",
        "Guaranteed miracle overnight results 100% clinically proven cure for diabetes!",
    ),
    (
        "financial",
        "Risk-free investment with guaranteed returns. Double your money this month.",
    ),
    (
        "political",
        "Vote for Smith. Paid for by Citizens for Change. Authorized by the candidate.",
    ),
    (
        "academic_fp",
        "Approximation and estimation error. Underfitting. Overfitting. "
        "hypothesis class size. statistical learning theory.",
    ),
    (
        "gambling",
        "Play real money casino online. Welcome bonus and risk-free bet today.",
    ),
]


def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 1)


def profile_legacy(texts: list[tuple[str, str]], rounds: int) -> dict:
    os.environ.setdefault("ZATAONE_DOCUMENT_CENTRIC", "1")
    from zataone.policy_engine.corpus.ontology_pack_builder import build_ontology_policy_pack
    from zataone.policy_engine.engine import PolicyEngine
    from zataone.schemas.document import DocumentSignal

    t0 = time.perf_counter()
    pack = build_ontology_policy_pack(jurisdiction="US", platform="all")
    load_ms = _ms(t0)
    assert pack is not None

    eng = PolicyEngine()
    eng.load_policy_pack(rules=pack.rules)

    # Warmup
    doc = DocumentSignal(
        asset_id=None,
        modality="text",
        normalized_text=texts[0][1],
    )
    eng.evaluate([], document=doc)

    per: list[dict] = []
    for name, text in texts:
        times = []
        n_viol = 0
        for _ in range(rounds):
            doc = DocumentSignal(asset_id=None, modality="text", normalized_text=text)
            t1 = time.perf_counter()
            viol = eng.evaluate([], document=doc)
            times.append(_ms(t1))
            n_viol = len(viol)
        per.append(
            {
                "sample": name,
                "avg_ms": round(sum(times) / len(times), 1),
                "min_ms": min(times),
                "max_ms": max(times),
                "violations": n_viol,
            }
        )
    return {"engine": "legacy_PolicyEngine", "pack_load_ms": load_ms, "rules": len(pack.rules), "samples": per}


def profile_hybrid(texts: list[tuple[str, str]], rounds: int, nlp_backend: str) -> dict:
    os.environ["ZATAONE_HYBRID_ENGINE"] = "1"
    os.environ["ZATAONE_HYBRID_NLP"] = "1"
    os.environ["ZATAONE_HYBRID_NLP_BACKEND"] = nlp_backend

    from zataone.policy_engine.hybrid.engine import HybridEngine
    from zataone.schemas.document import DocumentSignal

    t0 = time.perf_counter()
    eng = HybridEngine()
    init_ms = _ms(t0)

    doc = DocumentSignal(asset_id=None, modality="text", normalized_text=texts[0][1])
    eng.evaluate_full([], document=doc)

    per: list[dict] = []
    for name, text in texts:
        times = []
        n_viol = 0
        n_sig = 0
        for _ in range(rounds):
            doc = DocumentSignal(asset_id=None, modality="text", normalized_text=text)
            t1 = time.perf_counter()
            result = eng.evaluate_full([], document=doc)
            times.append(_ms(t1))
            n_viol = len(result.violations)
            n_sig = len(result.signals)
        per.append(
            {
                "sample": name,
                "avg_ms": round(sum(times) / len(times), 1),
                "min_ms": min(times),
                "max_ms": max(times),
                "violations": n_viol,
                "hybrid_signals": n_sig,
            }
        )
    return {
        "engine": f"hybrid_{nlp_backend}",
        "init_ms": init_ms,
        "packs": eng.pack_count,
        "nlp_backend": eng.last_result.nlp_backend,
        "samples": per,
    }


def profile_image_extractors(image_path: Path) -> dict:
    """OCR + DINO only (no Gemini) — usually the heavy local cost for images."""
    from zataone.domains.ad_compliance.extractors.ocr_extractor import OCRExtractor
    from zataone.domains.ad_compliance.extractors.vision_extractor import VisionExtractor

    asset = type("A", (), {"type": "image", "image_data": image_path.read_bytes(), "content": None})()
    out: dict = {"image": str(image_path), "bytes": image_path.stat().st_size}

    t0 = time.perf_counter()
    ocr = OCRExtractor()
    ocr_sigs = ocr.extract(asset)
    out["ocr_ms"] = _ms(t0)
    out["ocr_signals"] = len(ocr_sigs)

    t0 = time.perf_counter()
    vision = VisionExtractor()
    # First call may load DINO from disk into RAM (not Hub if cached/baked)
    vis_sigs = vision.extract(asset)
    out["dino_first_ms"] = _ms(t0)
    out["dino_signals"] = len(vis_sigs)

    t0 = time.perf_counter()
    vision.extract(asset)
    out["dino_second_ms"] = _ms(t0)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--nlp-backend", choices=("bow", "minilm", "auto"), default="bow")
    ap.add_argument("--image", type=Path, default=None, help="Optional image for OCR/DINO timing")
    ap.add_argument("--warmup", action="store_true", help="Time MiniLM Hub/cache load alone")
    args = ap.parse_args()

    print("=== Engine profile (local) ===\n")

    if args.warmup and args.nlp_backend in ("minilm", "auto"):
        os.environ["ZATAONE_HYBRID_NLP_BACKEND"] = "minilm"
        t0 = time.perf_counter()
        from zataone.policy_engine.hybrid.nlp import HybridNLPScorer

        scorer = HybridNLPScorer()
        print(f"MiniLM load+warmup: {_ms(t0)} ms (backend={scorer.backend})")
        t0 = time.perf_counter()
        scorer.encode(["guaranteed miracle cure"])
        print(f"MiniLM encode(1):   {_ms(t0)} ms\n")

    legacy = profile_legacy(SAMPLES, args.rounds)
    print(f"Legacy PolicyEngine  pack_load={legacy['pack_load_ms']}ms  rules={legacy['rules']}")
    for s in legacy["samples"]:
        print(
            f"  {s['sample']:20} avg={s['avg_ms']:7}ms  "
            f"min={s['min_ms']} max={s['max_ms']}  viol={s['violations']}"
        )

    print()
    hybrid = profile_hybrid(SAMPLES, args.rounds, args.nlp_backend)
    print(
        f"HybridEngine         init={hybrid['init_ms']}ms  packs={hybrid['packs']}  "
        f"nlp={hybrid['nlp_backend']}"
    )
    for s in hybrid["samples"]:
        print(
            f"  {s['sample']:20} avg={s['avg_ms']:7}ms  "
            f"min={s['min_ms']} max={s['max_ms']}  viol={s['violations']} sig={s['hybrid_signals']}"
        )

    if args.image and args.image.is_file():
        print("\n=== Image extractors (OCR + DINO, no Gemini) ===")
        img = profile_image_extractors(args.image)
        for k, v in img.items():
            print(f"  {k}: {v}")
        print(
            "\nNote: Full Cloud Run image path also adds Gemini VLM + advisory LLM "
            "(network), often larger than engine time."
        )
    else:
        print(
            "\n(Tip: pass --image path.png to time OCR+DINO locally. "
            "Full path also includes Gemini API latency.)"
        )

    print(
        "\nInterpretation:\n"
        "  - If engine averages are <100ms, slowness is NOT the rule engine.\n"
        "  - Image path: cold DINO load + OCR + Gemini dominate.\n"
        "  - Bake MiniLM in Docker (preload_models.py minilm) to avoid Hub download.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
