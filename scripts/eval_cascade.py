#!/usr/bin/env python3
"""Score the deterministic tier, the semantic tier, and the cascade over them, on one split.

The cascade is the point. Tier 1 answers where it has a rule and a licence check; tier 2 is
consulted only where tier 1 is silent, which is the population it was meant for — paraphrase
and implication with no prohibited string to match. Scoring the model on its own says
nothing about whether it belongs in the product; scoring the combination does.

Union is reported alongside as the naive alternative: let either tier fire. It buys recall
and pays for it in precision, and the numbers make the trade explicit rather than assumed.

Usage:
  PYTHONPATH=src python scripts/eval_cascade.py --split test
  PYTHONPATH=src python scripts/eval_cascade.py --split dev
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "ontology"))


def score(name: str, y: list[int], pred: list[bool]) -> dict:
    tp = sum(1 for a, b in zip(y, pred) if a == 1 and b)
    fp = sum(1 for a, b in zip(y, pred) if a == 0 and b)
    tn = sum(1 for a, b in zip(y, pred) if a == 0 and not b)
    fn = sum(1 for a, b in zip(y, pred) if a == 1 and not b)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    f2 = 5 * p * r / (4 * p + r) if p + r else 0.0
    spec = tn / (tn + fp) if tn + fp else 0.0
    return {"name": name, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "P": p, "R": r, "F1": f1, "F2": f2, "spec": spec}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--split", default="test")
    ap.add_argument("--threshold", type=float, default=None, help="override model threshold")
    args = ap.parse_args()

    os.environ["ZATAONE_EVAL_INCLUDE_HARVESTED"] = "1"
    os.environ["ZATAONE_EVAL_SPLITS"] = args.split
    os.environ.setdefault("ZATAONE_HYBRID_NLP", "0")

    from examples.load_eval import load_eval_with_sources
    from zataone.policy_engine.hybrid.engine import HybridEngine
    from zataone.policy_engine.ml.semantic_classifier import SemanticClassifier
    from zataone.schemas.document import DocumentSignal

    rows, sources = load_eval_with_sources(str(REPO / "ontology"))
    rows = [r for r in rows if (r.get("content") or "").strip()
            and r.get("label") in ("compliant", "non_compliant")]

    clf = SemanticClassifier()
    if not clf.available:
        print("no trained model — run ontology/tools/train_semantic_classifier.py", file=sys.stderr)
        return 1
    thr = args.threshold if args.threshold is not None else float(clf.meta.get("threshold", 0.5))

    eng = HybridEngine()
    y: list[int] = []
    det: list[bool] = []
    sem: list[bool] = []
    for r in rows:
        content = r["content"].strip()
        doc = DocumentSignal(asset_id=None, modality="text", normalized_text=content, spans=[],
                             scene_descriptions=[], source_signal_ids=[], timeline=[], metadata={})
        result = eng.evaluate_full([], document=doc, active_rule_ids=None)
        y.append(1 if r["label"] == "non_compliant" else 0)
        det.append(len(result.violations) > 0)
        s = clf.score(content)
        sem.append(bool(s is not None and s >= thr))

    # For a binary fire/no-fire decision, "consult tier 2 only where tier 1 is silent" is
    # the same predicate as "either tier fires" — d or (s and not d) reduces to d or s. The
    # cascade earns its name on cost, not on the decision: tier 2 runs on the silent
    # fraction only. Reported below as the invocation rate.
    cascade = [d or s for d, s in zip(det, sem)]
    # A genuinely different configuration: both tiers must agree. Trades recall for
    # precision, which is what a low-review-capacity deployment wants.
    confirmed = [d and s for d, s in zip(det, sem)]

    print(f"split={args.split}  rows={len(rows)}  model_threshold={thr:.2f}")
    print(f"model trained on {clf.meta.get('trained_on')}, tuned on {clf.meta.get('tuned_on')}, "
          f"dev AUC {clf.meta.get('dev_auc')}\n")

    header = f"{'configuration':<26}{'P':>7}{'R':>7}{'F1':>7}{'F2':>7}{'spec':>7}   TP/FP/TN/FN"
    print(header)
    print("-" * len(header))
    for res in (
        score("deterministic only", y, det),
        score("semantic only", y, sem),
        score("cascade (det or sem)", y, cascade),
        score("confirmed (det and sem)", y, confirmed),
    ):
        print(f"{res['name']:<26}{res['P']:>7.3f}{res['R']:>7.3f}{res['F1']:>7.3f}"
              f"{res['F2']:>7.3f}{res['spec']:>7.3f}   "
              f"{res['tp']}/{res['fp']}/{res['tn']}/{res['fn']}")

    # Per source file. The harvested rows are verbatim enforcement-document wording and the
    # pairs are model-written rewrites, so a classifier can score well by learning the
    # difference in register rather than anything about compliance. The seed rows are
    # expert-written in a third style: if the model holds up there, it learned more than
    # provenance.
    by_src: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        by_src.setdefault(sources.get(r["id"], "?"), []).append(i)
    print(f"\n{'source file':<34}{'n':>5}{'gold+':>7}{'det R':>8}{'sem R':>8}{'sem spec':>10}")
    for src, idx in sorted(by_src.items()):
        pos = [i for i in idx if y[i] == 1]
        neg = [i for i in idx if y[i] == 0]
        det_r = sum(det[i] for i in pos) / len(pos) if pos else float("nan")
        sem_r = sum(sem[i] for i in pos) / len(pos) if pos else float("nan")
        sem_s = sum(not sem[i] for i in neg) / len(neg) if neg else float("nan")
        print(f"{src:<34}{len(idx):>5}{len(pos):>7}{det_r:>8.3f}{sem_r:>8.3f}{sem_s:>10.3f}")

    print(f"\ntier 2 invoked on {sum(1 for d in det if not d)}/{len(rows)} rows "
          f"({sum(1 for d in det if not d) / len(rows):.0%} of traffic)")

    silent = [i for i, d in enumerate(det) if not d]
    if silent:
        caught = sum(1 for i in silent if sem[i] and y[i] == 1)
        missed_pos = sum(1 for i in silent if y[i] == 1)
        false_alarm = sum(1 for i in silent if sem[i] and y[i] == 0)
        clean = sum(1 for i in silent if y[i] == 0)
        print(f"\nWhere tier 1 is silent ({len(silent)} rows):")
        print(f"  violations tier 1 missed:      {missed_pos}")
        print(f"  of those, tier 2 recovers:     {caught}"
              f"  ({caught / missed_pos:.1%})" if missed_pos else "")
        print(f"  clean rows there:              {clean}")
        print(f"  of those, tier 2 false-alarms: {false_alarm}"
              f"  ({false_alarm / clean:.1%})" if clean else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
