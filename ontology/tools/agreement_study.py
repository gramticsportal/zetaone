#!/usr/bin/env python3
"""Inter-annotator agreement: how consistently do two people label the same ads?

The answer is the ceiling for any model. If two reviewers agree on 85% of ads,
a model at 95% agreement with gold is fitting one reviewer's habits, not the policy.

1. Draw a blind sample, stratified by category and label, with gold hidden:

     python3.11 ontology/tools/agreement_study.py sample --n 200 --out study.csv

   Give each annotator their own copy. They fill ``label`` with
   compliant | non_compliant | borderline and may add ``clause_ids`` and ``notes``.

2. Score two (or more) filled copies against each other and against gold:

     python3.11 ontology/tools/agreement_study.py score alice.csv bob.csv
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

ONTOLOGY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ONTOLOGY))

from examples.load_eval import load_eval_with_sources  # noqa: E402

LABELS = ("compliant", "non_compliant", "borderline")
SAMPLE_COLUMNS = ["id", "category_ids", "modality", "content", "label", "clause_ids", "notes"]


def stratified_sample(examples: list[dict], n: int, seed: int) -> list[dict]:
    """Round-robin over (category, label) cells so thin categories are represented."""
    rng = random.Random(seed)
    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for e in examples:
        cat = (e.get("category_ids") or ["(none)"])[0]
        cells[(cat, e.get("label"))].append(e)
    for rows in cells.values():
        rng.shuffle(rows)
    picked: list[dict] = []
    keys = sorted(cells)
    while len(picked) < n and any(cells[k] for k in keys):
        for k in keys:
            if cells[k] and len(picked) < n:
                picked.append(cells[k].pop())
    rng.shuffle(picked)
    return picked


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    n = len(a)
    if not n:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum(ca[k] * cb[k] for k in set(ca) | set(cb)) / (n * n)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def read_labels(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8") as f:
        return {
            row["id"]: row["label"].strip().lower()
            for row in csv.DictReader(f)
            if row.get("label", "").strip().lower() in LABELS
        }


def cmd_sample(args: argparse.Namespace) -> int:
    examples, _ = load_eval_with_sources(str(ONTOLOGY))
    picked = stratified_sample(examples, args.n, args.seed)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SAMPLE_COLUMNS)
        writer.writeheader()
        for e in picked:
            writer.writerow(
                {
                    "id": e["id"],
                    "category_ids": ",".join(e.get("category_ids") or []),
                    "modality": e.get("modality") or "",
                    "content": e.get("content") or "",
                    "label": "",
                    "clause_ids": "",
                    "notes": "",
                }
            )
    print(f"Wrote {len(picked)} blind rows to {args.out}")
    print("Cells:", dict(Counter((e.get("category_ids") or ["(none)"])[0] for e in picked)))
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    examples, _ = load_eval_with_sources(str(ONTOLOGY))
    gold = {e["id"]: e.get("label") for e in examples}
    annotators = {path.stem: read_labels(path) for path in args.files}

    print("Pairwise agreement")
    for (name_a, a), (name_b, b) in combinations(annotators.items(), 2):
        shared = sorted(set(a) & set(b))
        la, lb = [a[i] for i in shared], [b[i] for i in shared]
        raw = sum(x == y for x, y in zip(la, lb)) / len(shared) if shared else 0.0
        kappa = cohen_kappa(la, lb)
        print(f"  {name_a} vs {name_b}: n={len(shared)} raw={raw:.1%} kappa={kappa:.3f}")
        confusion = Counter((x, y) for x, y in zip(la, lb) if x != y)
        for (x, y), n in confusion.most_common(5):
            print(f"    {name_a}={x} / {name_b}={y}: {n}")

    print("Agreement with gold")
    for name, labels in annotators.items():
        shared = [i for i in labels if i in gold]
        agree = sum(labels[i] == gold[i] for i in shared)
        print(f"  {name}: n={len(shared)} agree={agree / len(shared):.1%}" if shared else f"  {name}: n=0")

    if len(annotators) >= 2:
        all_ids = set.intersection(*(set(v) for v in annotators.values()))
        disputed = [i for i in sorted(all_ids) if len({v[i] for v in annotators.values()}) > 1]
        print(f"Rows the annotators disagree on: {len(disputed)} (adjudicate these first)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_sample = sub.add_parser("sample", help="Draw a blind stratified sample")
    p_sample.add_argument("--n", type=int, default=200)
    p_sample.add_argument("--seed", type=int, default=20260927)
    p_sample.add_argument("--out", type=Path, required=True)
    p_score = sub.add_parser("score", help="Score filled copies")
    p_score.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args()
    return cmd_sample(args) if args.cmd == "sample" else cmd_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
