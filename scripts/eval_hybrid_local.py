#!/usr/bin/env python3
"""Phase C: local hybrid-only eval over ontology seed + precedent examples.

Usage (repo root):
  PYTHONPATH=src python scripts/eval_hybrid_local.py
  ZATAONE_EVAL_PROFILE=clean PYTHONPATH=src python scripts/eval_hybrid_local.py
"""

from __future__ import annotations

import os
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "ontology"))

os.environ.setdefault("ZATAONE_HYBRID_ENGINE", "1")
os.environ.setdefault("ZATAONE_HYBRID_NLP", "1")
os.environ.setdefault("ZATAONE_HYBRID_NLP_BACKEND", "bow")


def main() -> int:
    from examples.load_eval import load_eval_with_sources
    from zataone.policy_engine.hybrid.engine import HybridEngine
    from zataone.schemas.document import DocumentSignal

    examples, sources = load_eval_with_sources(str(ROOT / "ontology"))
    if not examples:
        print("No eval examples found", file=sys.stderr)
        return 1

    t0 = time.perf_counter()
    eng = HybridEngine()
    init_ms = (time.perf_counter() - t0) * 1000

    # Binary: non_compliant = positive; compliant = negative; borderline tracked separate
    tp = fp = tn = fn = 0
    borderline_hit = borderline_miss = 0
    by_label = Counter()
    by_cat_gold = defaultdict(lambda: {"tp": 0, "fn": 0, "fp_on_compliant": 0, "n_nc": 0, "n_c": 0})
    by_source = Counter()
    rows_fail: list[str] = []
    viol_counts: list[int] = []

    t_eval = time.perf_counter()
    for ex in examples:
        by_label[ex.get("label")] += 1
        by_source[sources.get(ex["id"], "?")] += 1
        content = (ex.get("content") or "").strip()
        doc = DocumentSignal(
            asset_id=None,
            modality=ex.get("modality") or "text",
            normalized_text=content,
            spans=[],
            scene_descriptions=[],
            source_signal_ids=[],
            timeline=[],
            metadata={"eval_id": ex.get("id")},
        )
        result = eng.evaluate_full([], document=doc, active_rule_ids=None)
        n_viol = len(result.violations)
        viol_counts.append(n_viol)
        pred_pos = n_viol > 0
        label = ex.get("label")
        gold_cats = set(ex.get("category_ids") or [])
        hit_cats = {
            (v.evidence_data or {}).get("category_id")
            for v in result.violations
            if (v.evidence_data or {}).get("category_id")
        }
        cat_hit = bool(gold_cats & hit_cats)

        if label == "non_compliant":
            if pred_pos:
                tp += 1
            else:
                fn += 1
                rows_fail.append(f"FN {ex['id']}: {content[:80]!r}")
            for c in gold_cats:
                by_cat_gold[c]["n_nc"] += 1
                if c in hit_cats:
                    by_cat_gold[c]["tp"] += 1
                else:
                    by_cat_gold[c]["fn"] += 1
        elif label == "compliant":
            if pred_pos:
                fp += 1
                rows_fail.append(
                    f"FP {ex['id']} cats={sorted(hit_cats)}: {content[:80]!r}"
                )
            else:
                tn += 1
            for c in gold_cats or {"_none"}:
                by_cat_gold[c]["n_c"] += 1
                if pred_pos:
                    by_cat_gold[c]["fp_on_compliant"] += 1
        elif label == "borderline":
            if pred_pos:
                borderline_hit += 1
            else:
                borderline_miss += 1

    eval_s = time.perf_counter() - t_eval
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0

    print("=== Hybrid-only local eval ===")
    print(f"examples:       {len(examples)}  (sources: {dict(by_source)})")
    print(f"labels:         {dict(by_label)}")
    print(f"packs:          {eng.pack_count}")
    print(f"nlp_backend:    {os.environ.get('ZATAONE_HYBRID_NLP_BACKEND')}")
    print(f"engine_init_ms: {init_ms:.1f}")
    print(f"eval_wall_s:    {eval_s:.2f}  ({1000*eval_s/len(examples):.2f} ms/ex)")
    print()
    print("--- Binary (positive = non_compliant; ignore borderline) ---")
    print(f"TP={tp}  FP={fp}  TN={tn}  FN={fn}")
    print(f"precision:      {prec:.3f}")
    print(f"recall:         {rec:.3f}")
    print(f"f1:             {f1:.3f}")
    print(f"specificity:    {spec:.3f}  (compliant correctly cleared)")
    print()
    print("--- Borderline (not scored in P/R) ---")
    print(f"fired:          {borderline_hit}/{borderline_hit + borderline_miss}")
    print()
    print("--- Per gold category (NC: category hit; C: FP rate) ---")
    print(f"{'category':20} {'n_nc':>5} {'cat_rec':>8} {'n_c':>5} {'fp_rate':>8}")
    for cat in sorted(by_cat_gold):
        if cat == "_none":
            continue
        s = by_cat_gold[cat]
        n_nc = s["n_nc"]
        n_c = s["n_c"]
        cat_rec = (s["tp"] / n_nc) if n_nc else float("nan")
        fp_rate = (s["fp_on_compliant"] / n_c) if n_c else float("nan")
        print(
            f"{cat:20} {n_nc:5d} {cat_rec:8.3f} {n_c:5d} {fp_rate:8.3f}"
            if n_nc or n_c
            else f"{cat:20}"
        )
    print()
    print(f"violations/ex:  mean={sum(viol_counts)/len(viol_counts):.2f}  "
          f"max={max(viol_counts)}  zero={sum(1 for v in viol_counts if v==0)}")
    print()
    print(f"--- Sample misses (up to 25 of {len(rows_fail)}) ---")
    for line in rows_fail[:25]:
        print(line)
    if len(rows_fail) > 25:
        print(f"... +{len(rows_fail) - 25} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
