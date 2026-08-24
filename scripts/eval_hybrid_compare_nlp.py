#!/usr/bin/env python3
"""Compare hybrid NLP backends on the full ontology eval set (local, hybrid-only).

Usage:
  PYTHONPATH=src python scripts/eval_hybrid_compare_nlp.py
  PYTHONPATH=src python scripts/eval_hybrid_compare_nlp.py --backends bow,minilm,bge_small
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "ontology"))

DEFAULT_BACKENDS = ("bow", "minilm", "minilm_l12", "bge_small", "e5_small")


def _run_one(backend: str) -> dict:
    # Fresh env + reimport-safe: construct engine after setting env
    os.environ["ZATAONE_HYBRID_ENGINE"] = "1"
    os.environ["ZATAONE_HYBRID_NLP"] = "1"
    os.environ["ZATAONE_HYBRID_NLP_BACKEND"] = backend
    os.environ.pop("ZATAONE_HYBRID_NLP_MODEL", None)

    from examples.load_eval import load_eval_with_sources
    from zataone.policy_engine.hybrid.engine import HybridEngine
    from zataone.schemas.document import DocumentSignal

    examples, _ = load_eval_with_sources(str(ROOT / "ontology"))

    t_load = time.perf_counter()
    eng = HybridEngine()
    load_s = time.perf_counter() - t_load
    active = None
    model_id = None
    if eng._nlp is not None:
        active = eng._nlp.backend
        model_id = getattr(eng._nlp, "model_id", None)

    tp = fp = tn = fn = 0
    t_eval = time.perf_counter()
    for ex in examples:
        doc = DocumentSignal(
            asset_id=None,
            modality=ex.get("modality") or "text",
            normalized_text=(ex.get("content") or "").strip(),
            spans=[],
            scene_descriptions=[],
            source_signal_ids=[],
            timeline=[],
            metadata={},
        )
        result = eng.evaluate_full([], document=doc, active_rule_ids=None)
        pred_pos = len(result.violations) > 0
        label = ex.get("label")
        if label == "non_compliant":
            if pred_pos:
                tp += 1
            else:
                fn += 1
        elif label == "compliant":
            if pred_pos:
                fp += 1
            else:
                tn += 1
        # borderline ignored in P/R
    eval_s = time.perf_counter() - t_eval
    n = len(examples)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    return {
        "backend_req": backend,
        "backend_active": active,
        "model_id": model_id,
        "n": n,
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "precision": prec,
        "recall": rec,
        "f1": f1,
        "load_s": load_s,
        "eval_s": eval_s,
        "ms_per_ex": 1000.0 * eval_s / n if n else 0.0,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--backends",
        default=",".join(DEFAULT_BACKENDS),
        help="Comma-separated backends (default: bow,minilm,minilm_l12,bge_small,e5_small)",
    )
    args = ap.parse_args()
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]

    print("=== Hybrid NLP backend compare (local, full eval set) ===\n")
    rows = []
    for b in backends:
        print(f"Running backend={b} ...", flush=True)
        try:
            row = _run_one(b)
        except Exception as e:
            print(f"  FAILED: {e}", flush=True)
            rows.append(
                {
                    "backend_req": b,
                    "backend_active": "FAILED",
                    "model_id": str(e)[:60],
                    "n": 0,
                    "tp": 0,
                    "fp": 0,
                    "tn": 0,
                    "fn": 0,
                    "precision": 0.0,
                    "recall": 0.0,
                    "f1": 0.0,
                    "load_s": 0.0,
                    "eval_s": 0.0,
                    "ms_per_ex": 0.0,
                }
            )
            continue
        rows.append(row)
        print(
            f"  active={row['backend_active']}  f1={row['f1']:.3f}  "
            f"P={row['precision']:.3f} R={row['recall']:.3f}  "
            f"eval={row['eval_s']:.1f}s ({row['ms_per_ex']:.1f} ms/ex)",
            flush=True,
        )

    print()
    hdr = (
        f"{'backend':12} {'active':12} {'P':>6} {'R':>6} {'F1':>6} "
        f"{'load_s':>8} {'eval_s':>8} {'ms/ex':>8}  model"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(
            f"{r['backend_req'][:12]:12} {str(r['backend_active'])[:12]:12} "
            f"{r['precision']:6.3f} {r['recall']:6.3f} {r['f1']:6.3f} "
            f"{r['load_s']:8.2f} {r['eval_s']:8.1f} {r['ms_per_ex']:8.1f}  "
            f"{r['model_id'] or '-'}"
        )
    print()
    print("Note: binary metrics ignore borderline; positive = non_compliant.")
    print("Lexical matchers still run for every backend; NLP is the variable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
