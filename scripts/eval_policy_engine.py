#!/usr/bin/env python3
"""
Benchmark the deterministic PolicyEngine text path against the shared eval set.

Protocol matches DETERMINISTIC_ENGINE_COFOUNDER_SYNC (apples-to-apples):
  - Same eval files: ontology/examples/eval_seed.yaml + eval_precedents.yaml
  - Positive = >= 1 violation from the deterministic core on text `content`
  - Text-only; no VLM, no OCR, no LLM advisory in the metrics
  - Reported separately:
      * Recall on the 44 precedents (north star)
      * P / R / F1 on seed NC+C (borderline ignored) and on clean seed+prec
      * Borderline positive rate (informational)
      * Per-category recall on non_compliant rows

Run from repo root:
    PYTHONPATH=src python scripts/eval_policy_engine.py
In docker:
    docker compose exec api python scripts/eval_policy_engine.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from collections import defaultdict
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, ROOT)

from ontology.examples.load_eval import load_eval_with_sources  # noqa: E402


def git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return "unknown"


def build_predict():
    """Return predict(content) -> list of violation rule_ids, using the real
    deterministic core (extractors -> document -> policy engine), no advisory."""
    from zataone.core.pipeline import CompliancePipeline

    pipeline = CompliancePipeline(domain="ad_compliance")
    rule_count = len(getattr(pipeline._policy_engine, "_rules", {}))

    def predict(content: str) -> list[str]:
        asset = SimpleNamespace(type="text", content=content)
        res = pipeline._run_deterministic_core(asset, run_pipeline_mode="full")
        return sorted({str(v.rule_id) for v in (res.get("violations_raw") or [])})

    return predict, rule_count


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f1


def main() -> None:
    examples, sources = load_eval_with_sources(os.path.join(ROOT, "ontology"))
    predict, rule_count = build_predict()

    print(f"engine=PolicyEngine(corpus) rules={rule_count} sha={git_sha()}")
    print(f"examples={len(examples)} "
          f"(seed={sum(1 for e in examples if sources[e['id']]=='eval_seed.yaml')}, "
          f"precedents={sum(1 for e in examples if sources[e['id']]=='eval_precedents.yaml')})")

    t0 = time.perf_counter()
    results = []  # (example, source, predicted_positive, rule_ids)
    for e in examples:
        rules = predict(str(e.get("content") or ""))
        results.append((e, sources[e["id"]], bool(rules), rules))
    total_ms = (time.perf_counter() - t0) * 1000
    print(f"latency: {total_ms/len(examples):.1f} ms/example ({total_ms/1000:.1f}s total)\n")

    # -- North star: recall on 44 precedents (all non_compliant) --------------
    prec_rows = [r for r in results if r[1] == "eval_precedents.yaml"]
    prec_hits = sum(1 for r in prec_rows if r[2])
    print(f"[precedents-44]  recall = {prec_hits/len(prec_rows):.3f} "
          f"({prec_hits}/{len(prec_rows)})   <-- north star (cofounder best: 0.818)")
    misses = [r[0]["id"] for r in prec_rows if not r[2]]
    if misses:
        print(f"  missed: {', '.join(misses)}")

    # -- Seed NC + C (borderline ignored) -------------------------------------
    def score(rows, name, note=""):
        tp = sum(1 for e, _, pos, _ in rows if e["label"] == "non_compliant" and pos)
        fn = sum(1 for e, _, pos, _ in rows if e["label"] == "non_compliant" and not pos)
        fp = sum(1 for e, _, pos, _ in rows if e["label"] == "compliant" and pos)
        p, r, f1 = prf(tp, fp, fn)
        print(f"[{name}]  P={p:.3f} R={r:.3f} F1={f1:.3f} "
              f"(TP={tp} FP={fp} FN={fn}){'   ' + note if note else ''}")

    seed_rows = [r for r in results if r[1] == "eval_seed.yaml"]
    seed_ncc = [r for r in seed_rows if r[0]["label"] in ("non_compliant", "compliant")]
    score(seed_ncc, "seed NC+C (380)")
    score(seed_ncc + prec_rows, "clean seed+prec (424)", "(cofounder best: F1 0.634)")

    borderline = [r for r in seed_rows if r[0]["label"] == "borderline"]
    if borderline:
        bpos = sum(1 for r in borderline if r[2])
        print(f"[borderline]  positive rate = {bpos/len(borderline):.3f} "
              f"({bpos}/{len(borderline)}) (informational)")

    # -- Per-category recall on non_compliant rows ----------------------------
    print("\nper-category (non_compliant recall | compliant FP rate):")
    by_cat: dict[str, dict[str, list]] = defaultdict(lambda: {"nc": [], "c": []})
    for e, src, pos, _ in seed_ncc:
        for cat in e.get("category_ids") or ["?"]:
            key = "nc" if e["label"] == "non_compliant" else "c"
            by_cat[cat][key].append(pos)
    for cat in sorted(by_cat):
        nc, c = by_cat[cat]["nc"], by_cat[cat]["c"]
        rec = sum(nc) / len(nc) if nc else 0.0
        fpr = sum(c) / len(c) if c else 0.0
        print(f"  {cat:<18} R={rec:.2f} ({sum(nc)}/{len(nc)})   FP={fpr:.2f} ({sum(c)}/{len(c)})")


if __name__ == "__main__":
    main()
