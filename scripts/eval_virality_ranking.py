#!/usr/bin/env python
"""
Does the Virality Index order creatives better than chance?

That is the only question about the Index that can be answered honestly today, and
it is the one that matters commercially: test budget is scarce, so "which three of
these twelve should we run first" is worth money even when "will this go viral" is
unanswerable.

**Method.** Within each comparison set — variants that ran under the same conditions —
rank by predicted Index and by observed performance, then take Spearman's rho between
the two orderings. Averaging rho across sets, never pooling variants across campaigns,
is what keeps spend and audience from doing the work.

**The baseline is the point.** A rho that looks respectable means nothing without the
null: with 3 variants there are only 6 orderings, and a third of them correlate
positively by luck. This script therefore permutes each set's predictions many times
and reports where the real score falls in that distribution. If the Index cannot beat
a shuffle, it is not a ranker, whatever its average rho.

Usage::

    python scripts/eval_virality_ranking.py --outcomes ontology/examples/outcomes/outcomes_seed.json
    python scripts/eval_virality_ranking.py --outcomes <file> --include-flagged --json out.json

With no scorer wired in, predictions come from the offline heuristic so the harness is
runnable today; pass ``--scored`` with a JSON map of ``{outcome_id: virality_index}``
to score a real model run instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from zataone.schemas.creative_outcome import ComparisonSet, OutcomeCorpus  # noqa: E402

PERMUTATIONS = 2000


def _stable_seed(value: str) -> int:
    """Process-independent seed; Python's built-in hash is randomized per interpreter."""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _ranks(values: list[float]) -> list[float]:
    """Fractional ranks, ties averaged — ties are common in coarse grades."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    """Pearson on ranks. None when either side is constant and rho is undefined."""
    if len(a) != len(b) or len(a) < 2:
        return None
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    da = sum((x - ma) ** 2 for x in ra)
    db = sum((y - mb) ** 2 for y in rb)
    if da == 0 or db == 0:
        return None
    return num / (da * db) ** 0.5


def heuristic_predictions(cs: ComparisonSet) -> dict[str, float]:
    """Fallback predictor: the shipped offline heuristic, scored on the variant label."""
    from zataone.services.virality_review_service import score_virality_offline

    out: dict[str, float] = {}
    for o in cs.outcomes:
        text = o.variant_label or o.notes or ""
        out[o.outcome_id] = float(score_virality_offline(text).get("virality_index", 0))
    return out


def score_set(cs: ComparisonSet, preds: dict[str, float]) -> dict[str, Any] | None:
    """Real rho for one set, plus its permutation null."""
    pairs = [
        (preds[o.outcome_id], o.rank_value())
        for o in cs.outcomes
        if o.outcome_id in preds and o.rank_value() is not None
    ]
    if len(pairs) < 2:
        return None

    pred = [p for p, _ in pairs]
    obs = [a for _, a in pairs]
    rho = spearman(pred, obs)
    if rho is None:
        return None

    shuffled = pred[:]
    null: list[float] = []
    rng = random.Random(_stable_seed(cs.campaign_id))
    for _ in range(PERMUTATIONS):
        rng.shuffle(shuffled)
        r = spearman(shuffled, obs)
        if r is not None:
            null.append(r)

    beat = sum(1 for r in null if r < rho) / len(null) if null else float("nan")
    return {
        "campaign_id": cs.campaign_id,
        "variants": len(pairs),
        "rho": round(rho, 4),
        "percentile_vs_shuffle": round(beat, 4),
        "warnings": cs.comparability_warnings(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outcomes", required=True, type=Path)
    ap.add_argument(
        "--scored",
        type=Path,
        help="JSON {outcome_id: virality_index} from a real run; omit to use the heuristic",
    )
    ap.add_argument(
        "--include-flagged",
        action="store_true",
        help="Include sets that comparability_warnings() flags as unfair fights",
    )
    ap.add_argument("--json", type=Path, help="Write the full per-set report here")
    args = ap.parse_args()

    corpus = OutcomeCorpus.model_validate_json(args.outcomes.read_text(encoding="utf-8"))
    summary = corpus.summary()
    print("Corpus:", json.dumps(summary, indent=2))

    external: dict[str, float] = {}
    if args.scored:
        external = {
            str(k): float(v)
            for k, v in json.loads(args.scored.read_text(encoding="utf-8")).items()
        }

    rows: list[dict[str, Any]] = []
    skipped_flagged = 0
    for cs in corpus.rankable_sets():
        warns = cs.comparability_warnings()
        if warns and not args.include_flagged:
            skipped_flagged += 1
            continue
        preds = external or heuristic_predictions(cs)
        row = score_set(cs, preds)
        if row:
            rows.append(row)

    print(f"\nScored {len(rows)} set(s); skipped {skipped_flagged} flagged as unfair fights.")
    if not rows:
        print(
            "\nNothing scoreable. This is the expected result on the seed file: it is "
            "illustrative, not observed. Point --outcomes at real partner data."
        )
        return 0

    for r in rows:
        mark = "  [flagged]" if r["warnings"] else ""
        print(
            f"  {r['campaign_id']:<44} n={r['variants']}  "
            f"rho={r['rho']:+.3f}  beats {r['percentile_vs_shuffle']:.0%} of shuffles{mark}"
        )

    rhos = [r["rho"] for r in rows]
    pcts = [r["percentile_vs_shuffle"] for r in rows]
    mean_rho = statistics.fmean(rhos)
    mean_pct = statistics.fmean(pcts)

    print(f"\n  mean rho                 {mean_rho:+.4f}")
    print(f"  mean percentile vs null  {mean_pct:.1%}   (50% = indistinguishable from chance)")
    print(f"  sets                     {len(rows)}")

    # A single campaign cannot establish a ranker, whatever it scores.
    if len(rows) < 20:
        print(
            f"\n  NOTE: {len(rows)} sets is far too few to conclude anything. "
            "Treat this as a plumbing check, not a result."
        )
    elif mean_pct < 0.60:
        print("\n  VERDICT: not distinguishable from shuffling. The Index is not a ranker yet.")
    else:
        print(f"\n  VERDICT: beats shuffle on average ({mean_pct:.0%}). Worth fitting weights.")

    if args.json:
        args.json.write_text(
            json.dumps(
                {"corpus": summary, "mean_rho": mean_rho, "mean_percentile": mean_pct, "sets": rows},
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nWrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
