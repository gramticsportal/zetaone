#!/usr/bin/env python3
"""Train the semantic classifier on the train split and tune its threshold on dev.

The deterministic tier misses a named class of cases — the benchmark lists 24 precedents
both engines fail, clustering into undisclosed-promotion and implied-claim wording where
no prohibited string appears. Those need a model that reads the whole sentence.

What this can and cannot do is worth stating before the numbers arrive. The compliant
minimal pairs were built to *retain* the violation's trigger wording, so vocabulary
carries almost no information on that subset by construction. Expect gains on paraphrase
and implication, and expect roughly nothing on pairs. The report prints those two
populations separately so the distinction cannot be lost in an average.

Splits are grouped by source enforcement action, so a case cannot straddle train and dev.
Test is never read here; scoring against it is a separate, later step.

Writes:
  ontology/models/semantic_classifier.npz
  ontology/models/semantic_classifier_report.md

Usage:
  python ontology/tools/train_semantic_classifier.py
  python ontology/tools/train_semantic_classifier.py --l2 1e-3 --iterations 600
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import numpy as np

ONTOLOGY = Path(__file__).resolve().parent.parent
REPO = ONTOLOGY.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(ONTOLOGY))

OUT_MODEL = ONTOLOGY / "models" / "semantic_classifier.npz"
OUT_REPORT = ONTOLOGY / "models" / "semantic_classifier_report.md"


def load_split(split: str) -> list[dict]:
    os.environ["ZATAONE_EVAL_INCLUDE_HARVESTED"] = "1"
    from examples.load_eval import load_eval_with_sources

    os.environ["ZATAONE_EVAL_SPLITS"] = split
    rows, sources = load_eval_with_sources(str(ONTOLOGY))
    for r in rows:
        r["_source_file"] = sources.get(r["id"], "?")
    return [r for r in rows if (r.get("content") or "").strip() and r.get("label") in ("compliant", "non_compliant")]


def metrics(y: np.ndarray, p: np.ndarray, thr: float) -> dict:
    pred = p >= thr
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn, "precision": prec, "recall": rec, "f1": f1}


def auc(y: np.ndarray, p: np.ndarray) -> float:
    """Rank-based AUC (Mann-Whitney), ties averaged."""
    order = np.argsort(p, kind="mergesort")
    ranks = np.empty(len(p), dtype=np.float64)
    ranks[order] = np.arange(1, len(p) + 1)
    # average ranks within tied score groups
    sp = p[order]
    i = 0
    while i < len(sp):
        j = i
        while j + 1 < len(sp) and sp[j + 1] == sp[i]:
            j += 1
        if j > i:
            ranks[order[i : j + 1]] = (i + j + 2) / 2.0
        i = j + 1
    n_pos = float(y.sum())
    n_neg = float(len(y) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return 0.5
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--l2", type=float, default=1e-4)
    ap.add_argument("--iterations", type=int, default=400)
    ap.add_argument("--learning-rate", type=float, default=2.0)
    ap.add_argument("--min-df", type=int, default=2)
    ap.add_argument("--max-features", type=int, default=20000)
    args = ap.parse_args()

    from zataone.policy_engine.ml.semantic_classifier import (
        TrainedModel,
        build_vocabulary,
        featurize,
        train_logistic,
    )

    train = load_split("train")
    dev = load_split("dev")
    if not train or not dev:
        print("no training rows — run ontology/tools/build_eval_splits.py first", file=sys.stderr)
        return 1

    tr_text = [r["content"] for r in train]
    tr_y = np.array([1.0 if r["label"] == "non_compliant" else 0.0 for r in train])
    dv_text = [r["content"] for r in dev]
    dv_y = np.array([1.0 if r["label"] == "non_compliant" else 0.0 for r in dev])

    vocab = build_vocabulary(tr_text, min_df=args.min_df, max_features=args.max_features)
    Xtr = featurize(tr_text, vocab)
    Xdv = featurize(dv_text, vocab)

    w, b, history = train_logistic(
        Xtr, tr_y, l2=args.l2, iterations=args.iterations, learning_rate=args.learning_rate
    )

    p_dv = 1.0 / (1.0 + np.exp(-(Xdv.astype(np.float64) @ w + b)))
    dev_auc = auc(dv_y, p_dv)

    # Threshold chosen on dev, for F1. Recorded rather than hardcoded so the choice is
    # visible and re-derivable.
    best_thr, best_f1 = 0.5, -1.0
    for thr in np.arange(0.05, 0.96, 0.01):
        m = metrics(dv_y, p_dv, float(thr))
        if m["f1"] > best_f1:
            best_thr, best_f1 = float(thr), m["f1"]
    dev_m = metrics(dv_y, p_dv, best_thr)

    # The two populations that must not be averaged together.
    is_pair = np.array([r["_source_file"] == "eval_compliant_pairs.yaml" for r in dev])
    pair_idx = np.where(is_pair)[0]
    pair_cleared = int((p_dv[pair_idx] < best_thr).sum()) if len(pair_idx) else 0
    harv_idx = np.array([i for i, r in enumerate(dev) if r["_source_file"] == "eval_harvested.yaml"])
    harv_rec = float((p_dv[harv_idx] >= best_thr).mean()) if len(harv_idx) else float("nan")

    meta = {
        "trained_on": "train",
        "tuned_on": "dev",
        "train_rows": len(train),
        "dev_rows": len(dev),
        "features": int(Xtr.shape[1]),
        "vocab": len(vocab),
        "l2": args.l2,
        "iterations": args.iterations,
        "dev_auc": round(dev_auc, 4),
        "threshold": round(best_thr, 3),
        "date": str(date.today()),
    }
    model = TrainedModel(weights=w, bias=b, vocab=vocab, threshold=best_thr, meta=meta)
    model.save(OUT_MODEL)

    lines = [
        "# Semantic classifier — training report",
        "",
        f"**Date:** {date.today()} · trained on `train`, tuned on `dev`, `test` untouched",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| Train rows | {len(train)} |",
        f"| Dev rows | {len(dev)} |",
        f"| Features | {Xtr.shape[1]} ({len(vocab)} n-gram + structural) |",
        f"| L2 | {args.l2} |",
        f"| Iterations | {args.iterations} (loss {history[0]:.4f} -> {history[-1]:.4f}) |",
        "",
        "## Dev performance",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| AUC | **{dev_auc:.3f}** |",
        f"| Threshold (tuned on dev) | {best_thr:.2f} |",
        f"| Precision | {dev_m['precision']:.3f} |",
        f"| Recall | {dev_m['recall']:.3f} |",
        f"| F1 | {dev_m['f1']:.3f} |",
        f"| TP/FP/TN/FN | {dev_m['tp']}/{dev_m['fp']}/{dev_m['tn']}/{dev_m['fn']} |",
        "",
        "## The two populations, kept apart",
        "",
        f"- **Harvested violations** (real enforcement wording): recall **{harv_rec:.3f}** on {len(harv_idx)} rows.",
        f"- **Compliant minimal pairs** (built to share the violation's vocabulary): "
        f"correctly cleared **{pair_cleared}/{len(pair_idx)}**"
        + (f" ({pair_cleared / len(pair_idx):.1%})" if len(pair_idx) else ""),
        "",
        "The pair number is the honest test of whether this model learned the rule or the",
        "vocabulary. Pairs share trigger words with their violations by construction, so a",
        "bag-of-words model has almost no signal there — and that is exactly why the",
        "qualifier gate, not this model, remains the discriminative layer.",
        "",
        "## Reproducing",
        "",
        "```bash",
        "python ontology/tools/train_semantic_classifier.py",
        "```",
        "",
        "Zero initialisation, no shuffling, fixed iteration count, vocabulary built by",
        "sorted document frequency: the same split produces the same weights byte for byte.",
    ]
    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    with OUT_REPORT.open("w", encoding="utf-8", newline="") as f:
        f.write("\n".join(lines) + "\n")

    print(f"train={len(train)} dev={len(dev)} features={Xtr.shape[1]}")
    print(f"loss {history[0]:.4f} -> {history[-1]:.4f}")
    print(f"dev AUC={dev_auc:.3f}  thr={best_thr:.2f}  "
          f"P={dev_m['precision']:.3f} R={dev_m['recall']:.3f} F1={dev_m['f1']:.3f}")
    print(f"harvested recall={harv_rec:.3f}   pairs cleared={pair_cleared}/{len(pair_idx)}")
    print(f"\nwrote {OUT_MODEL.relative_to(REPO)}\nwrote {OUT_REPORT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
