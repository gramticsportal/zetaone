#!/usr/bin/env python3
"""Assign train/dev/test splits to the harvested eval rows, grouped by source precedent.

Every harvested row and every compliant minimal pair currently carries `split: test`.
That is not a holdout, it is a label, and it makes the set unusable for training a
semantic tier and unreliable for scoring the deterministic one.

Two kinds of leakage have to be closed, and a random row-level split closes neither:

1. **Pair leakage.** Each compliant row is a rewrite of one specific violation —
   "No loans, no debt" against "No upfront tuition loans, no traditional debt during
   the program." Put one in train and its twin in test and a model scores well by
   recognising the sentence, not the rule.
2. **Case leakage.** 1,589 rows come from only 827 enforcement actions; the TurboTax
   case alone supplies 27. Rows from one case repeat the same claim wording, so
   splitting them apart leaks the case across the boundary.

Both are fixed by making the **source precedent** the unit of assignment: a case and
everything derived from it — violations and their pairs — land in exactly one split.

The 44 expert-labelled precedent rows stay the untouched north star. 13 of their cases
also appear in the harvested set, so those cases are **locked to test**: training on a
harvested sibling of a north-star row would quietly contaminate the headline metric.

Assignment is a stable hash of the precedent id, not a shuffle, so re-running is a no-op
and harvesting new cases never reshuffles the ones already assigned.

Writes:
  - ontology/examples/eval/eval_harvested.yaml        (split: lines only)
  - ontology/examples/eval/eval_compliant_pairs.yaml  (split: lines only)
  - ontology/examples/eval/eval_splits.yaml           (group -> split manifest)

Usage:
  python ontology/tools/build_eval_splits.py --dry-run
  python ontology/tools/build_eval_splits.py
  python ontology/tools/build_eval_splits.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
EVAL = ONTOLOGY / "examples" / "eval"

HARVESTED = EVAL / "eval_harvested.yaml"
PAIRS = EVAL / "eval_compliant_pairs.yaml"
PRECEDENTS = EVAL / "eval_precedents.yaml"
MANIFEST = EVAL / "eval_splits.yaml"

# Fractions are cumulative over a stable hash of the group id. Adding groups later
# shifts nobody: each group's bucket depends only on its own id.
TRAIN_UPTO = 0.70
DEV_UPTO = 0.85

PAIR_SUFFIX = "_compliant"

_DERIVED_RE = re.compile(r"derived_from:\s*([^\s;]+)")
_PAIR_OF_RE = re.compile(r"compliant minimal pair of\s+([^\s;]+)")

_ROW_START_RE = re.compile(r"^- id:\s*(\S+)\s*$")
_SPLIT_LINE_RE = re.compile(r"^(\s*)split:\s*\S+\s*$")


def load_examples(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("examples") or []


def precedent_of(example: dict) -> str | None:
    """Source enforcement action a row was derived from, from its note."""
    m = _DERIVED_RE.search(example.get("note") or "")
    return m.group(1) if m else None


def parent_of(example: dict) -> str | None:
    """Harvested row a compliant pair was built from."""
    m = _PAIR_OF_RE.search(example.get("note") or "")
    if m:
        return m.group(1)
    rid = example.get("id") or ""
    return rid[: -len(PAIR_SUFFIX)] if rid.endswith(PAIR_SUFFIX) else None


def bucket(group_id: str) -> str:
    digest = hashlib.sha1(group_id.encode("utf-8")).hexdigest()[:8]
    frac = int(digest, 16) / 0xFFFFFFFF
    if frac < TRAIN_UPTO:
        return "train"
    if frac < DEV_UPTO:
        return "dev"
    return "test"


def build_groups() -> tuple[dict[str, str], dict[str, str], dict]:
    """Return (row_id -> group_id, group_id -> split, stats)."""
    harvested = load_examples(HARVESTED)
    pairs = load_examples(PAIRS)
    north_star = load_examples(PRECEDENTS)

    # Cases behind the 44 expert rows: never available for training.
    locked = {p for p in (precedent_of(e) for e in north_star) if p}

    row_group: dict[str, str] = {}
    unresolved: list[str] = []

    for e in harvested:
        rid = e["id"]
        # A row with no traceable case is its own group: still safe, just not pooled.
        group = precedent_of(e) or rid
        if precedent_of(e) is None:
            unresolved.append(rid)
        row_group[rid] = group

    orphan_pairs: list[str] = []
    for e in pairs:
        rid = e["id"]
        parent = parent_of(e)
        if parent and parent in row_group:
            row_group[rid] = row_group[parent]
        else:
            orphan_pairs.append(rid)
            row_group[rid] = rid

    groups = sorted(set(row_group.values()))
    group_split = {g: ("test" if g in locked else bucket(g)) for g in groups}

    stats = {
        "harvested_rows": len(harvested),
        "pair_rows": len(pairs),
        "groups": len(groups),
        "locked_groups": sum(1 for g in groups if g in locked),
        "north_star_cases": len(locked),
        "rows_without_precedent": len(unresolved),
        "pairs_without_parent": len(orphan_pairs),
    }
    return row_group, group_split, stats


def rewrite_splits(path: Path, row_split: dict[str, str], dry_run: bool) -> tuple[int, int]:
    """Rewrite only the `split:` line of each row. Returns (changed, total)."""
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    out: list[str] = []
    current: str | None = None
    changed = 0
    seen = 0

    for line in lines:
        m = _ROW_START_RE.match(line.rstrip("\n"))
        if m:
            current = m.group(1)
            seen += 1
            out.append(line)
            continue
        sm = _SPLIT_LINE_RE.match(line.rstrip("\n"))
        if sm and current is not None:
            want = row_split.get(current)
            if want is None:
                out.append(line)
                continue
            newline = f"{sm.group(1)}split: {want}\n"
            if newline != line:
                changed += 1
            out.append(newline)
            continue
        out.append(line)

    if not dry_run:
        with path.open("w", encoding="utf-8", newline="") as f:
            f.write("".join(out))
    return changed, seen


def write_manifest(group_split: dict[str, str], stats: dict, dry_run: bool) -> None:
    by_split = Counter(group_split.values())
    doc = {
        "schema_version": 1,
        "unit": "source_precedent",
        "policy": [
            "A source enforcement action and every row derived from it — violations and "
            "their compliant minimal pairs — share one split.",
            "Cases behind the 44 expert precedent rows are locked to test.",
            "Assignment is a stable hash of the precedent id, so adding cases never "
            "reshuffles existing ones.",
        ],
        "ratios": {"train": TRAIN_UPTO, "dev": DEV_UPTO - TRAIN_UPTO, "test": 1 - DEV_UPTO},
        "stats": stats,
        "groups_by_split": dict(sorted(by_split.items())),
        "groups": dict(sorted(group_split.items())),
    }
    if not dry_run:
        with MANIFEST.open("w", encoding="utf-8", newline="") as f:
            f.write("# Generated by ontology/tools/build_eval_splits.py — do not hand-edit.\n")
            yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True, width=100)


def check() -> int:
    """Verify no group and no duplicate content spans two splits."""
    row_group, group_split, stats = build_groups()
    rows = load_examples(HARVESTED) + load_examples(PAIRS)

    problems: list[str] = []

    group_seen: dict[str, set[str]] = defaultdict(set)
    content_seen: dict[str, set[str]] = defaultdict(set)
    for e in rows:
        rid = e["id"]
        split = e.get("split")
        group_seen[row_group.get(rid, rid)].add(str(split))
        content_seen[(e.get("content") or "").strip().lower()].add(str(split))

    for g, splits in group_seen.items():
        if len(splits) > 1:
            problems.append(f"group {g} spans splits {sorted(splits)}")
    for c, splits in content_seen.items():
        if len(splits) > 1:
            problems.append(f"duplicate content spans splits {sorted(splits)}: {c[:60]!r}")

    expected = {rid: group_split[row_group[rid]] for rid in row_group}
    for e in rows:
        want = expected.get(e["id"])
        if want and e.get("split") != want:
            problems.append(f"{e['id']}: split {e.get('split')!r}, expected {want!r}")

    north_star = load_examples(PRECEDENTS)
    for e in north_star:
        if e.get("split") != "test":
            problems.append(f"north-star row {e['id']} is not test")

    counts = Counter(e.get("split") for e in rows)
    print("rows by split:", dict(sorted(counts.items())))
    print("groups by split:", dict(sorted(Counter(group_split.values()).items())))

    if problems:
        print(f"\nFAIL — {len(problems)} problem(s):")
        for p in problems[:20]:
            print("  -", p)
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")
        return 1
    print("\nOK — no group or duplicate content spans splits; north star is test-only.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="report without writing")
    ap.add_argument("--check", action="store_true", help="verify existing splits, write nothing")
    args = ap.parse_args()

    if args.check:
        return check()

    row_group, group_split, stats = build_groups()
    row_split = {rid: group_split[g] for rid, g in row_group.items()}

    h_changed, h_seen = rewrite_splits(HARVESTED, row_split, args.dry_run)
    p_changed, p_seen = rewrite_splits(PAIRS, row_split, args.dry_run)
    write_manifest(group_split, stats, args.dry_run)

    rows_by_split = Counter(row_split.values())
    groups_by_split = Counter(group_split.values())
    total = sum(rows_by_split.values()) or 1

    print(f"{'DRY RUN — nothing written' if args.dry_run else 'written'}")
    print(f"  harvested : {h_changed}/{h_seen} split lines changed")
    print(f"  pairs     : {p_changed}/{p_seen} split lines changed")
    print(f"  groups    : {stats['groups']} ({stats['locked_groups']} locked to test)")
    if stats["rows_without_precedent"]:
        print(f"  warning   : {stats['rows_without_precedent']} rows had no derived_from")
    if stats["pairs_without_parent"]:
        print(f"  warning   : {stats['pairs_without_parent']} pairs had no resolvable parent")
    print("\n  split   groups     rows    share")
    for s in ("train", "dev", "test"):
        print(f"  {s:<7}{groups_by_split[s]:>7}{rows_by_split[s]:>9}{rows_by_split[s] / total:>8.1%}")

    if h_seen != stats["harvested_rows"] or p_seen != stats["pair_rows"]:
        print("\nERROR: row count from line scan disagrees with parsed YAML", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
