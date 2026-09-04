#!/usr/bin/env python3
"""Apply human_decision values from eval_gold_review.csv to the eval YAMLs.

Reads ontology/examples/harvest/eval_gold_review.csv after you fill human_decision:

  keep         — no change
  drop         — remove row from its eval YAML (and twin pair if harvested)
  quarantine   — same as drop, but append to harvest/eval_manual_quarantine.yaml
  relabel_nc   — set label to non_compliant
  relabel_c    — set label to compliant

Dry-run by default. Pass --apply to write.

Usage:
  python3.11 ontology/tools/apply_eval_gold_decisions.py
  python3.11 ontology/tools/apply_eval_gold_decisions.py --apply
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import yaml

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
EVAL = EXAMPLES / "eval"
HARVEST = EXAMPLES / "harvest"
REVIEW = HARVEST / "eval_gold_review.csv"
QUAR = HARVEST / "eval_manual_quarantine.yaml"

FILE_BY_SOURCE = {
    "eval_seed.yaml": EVAL / "eval_seed.yaml",
    "eval_precedents.yaml": EVAL / "eval_precedents.yaml",
    "eval_harvested.yaml": EVAL / "eval_harvested.yaml",
    "eval_compliant_pairs.yaml": EVAL / "eval_compliant_pairs.yaml",
}


def load_examples(path: Path) -> tuple[str, list[dict]]:
    raw = path.read_text(encoding="utf-8")
    # Keep YAML preamble comments roughly: dump will rewrite; fine for now.
    doc = yaml.safe_load(raw) or {}
    return raw.split("examples:", 1)[0] if "examples:" in raw else "", list(doc.get("examples") or [])


def dump_examples(path: Path, preamble: str, examples: list[dict]) -> None:
    body = yaml.safe_dump({"examples": examples}, sort_keys=False, allow_unicode=True, width=1000)
    if preamble and not preamble.endswith("\n"):
        preamble += "\n"
    path.write_text((preamble or "") + body, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--csv", default=str(REVIEW))
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.exists():
        print(f"missing {path} — run audit_eval_gold.py first", file=sys.stderr)
        return 2

    decisions = [
        r
        for r in csv.DictReader(path.open(encoding="utf-8"))
        if (r.get("human_decision") or "").strip()
    ]
    if not decisions:
        print("no human_decision values filled yet")
        return 0

    by_id = {r["id"]: r for r in decisions}
    counts = {"keep": 0, "drop": 0, "quarantine": 0, "relabel_nc": 0, "relabel_c": 0, "unknown": 0}
    quarantined: list[dict] = []

    for source, fpath in FILE_BY_SOURCE.items():
        if not fpath.exists():
            continue
        preamble, examples = load_examples(fpath)
        kept: list[dict] = []
        changed = False
        for ex in examples:
            eid = ex.get("id")
            d = by_id.get(eid)
            if not d:
                kept.append(ex)
                continue
            action = (d.get("human_decision") or "").strip().lower()
            if action in ("", "keep"):
                counts["keep"] += 1
                kept.append(ex)
                continue
            if action in ("drop", "quarantine"):
                counts[action if action in counts else "drop"] += 1
                changed = True
                if action == "quarantine":
                    quarantined.append(ex)
                # Also drop twin pair when dropping a harvested NC
                continue
            if action == "relabel_nc":
                counts["relabel_nc"] += 1
                if ex.get("label") != "non_compliant":
                    ex = dict(ex)
                    ex["label"] = "non_compliant"
                    changed = True
                kept.append(ex)
                continue
            if action == "relabel_c":
                counts["relabel_c"] += 1
                if ex.get("label") != "compliant":
                    ex = dict(ex)
                    ex["label"] = "compliant"
                    changed = True
                kept.append(ex)
                continue
            counts["unknown"] += 1
            kept.append(ex)

        # Drop compliant twins of dropped harvested ids
        dropped_ids = {
            r["id"]
            for r in decisions
            if (r.get("human_decision") or "").strip().lower() in ("drop", "quarantine")
            and r.get("source") == "eval_harvested.yaml"
        }
        if source == "eval_compliant_pairs.yaml" and dropped_ids:
            before = len(kept)
            kept = [e for e in kept if e.get("id", "").removesuffix("_compliant") not in dropped_ids]
            if len(kept) != before:
                changed = True

        print(f"{source}: {len(examples)} → {len(kept)}" + (" (changed)" if changed else ""))
        if args.apply and changed:
            dump_examples(fpath, preamble, kept)

    if quarantined:
        print(f"quarantine candidates: {len(quarantined)}")
        if args.apply:
            existing = []
            if QUAR.exists():
                existing = list((yaml.safe_load(QUAR.read_text(encoding="utf-8")) or {}).get("examples") or [])
            seen = {e.get("id") for e in existing}
            for e in quarantined:
                if e.get("id") not in seen:
                    existing.append(e)
            dump_examples(
                QUAR,
                "# Manually quarantined from eval_gold_review.csv. Not loaded by load_eval.py.\n\n",
                existing,
            )
            print(f"wrote {QUAR}")

    print("counts:", counts)
    if not args.apply:
        print("dry-run only — re-run with --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
