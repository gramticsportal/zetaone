#!/usr/bin/env python3
"""Rank eval rows whose gold label the systems disagree with, for human audit.

Input is a run of ``scripts/eval_local_review.py`` (rows carry ``matcher_display``,
``local_display`` and, when a Gemini baseline was used, ``gemini_display``). A row
is queued when at least half of the systems that scored it disagree with its label:

  high    every system disagrees (the likeliest bad gold, or a shared blind spot)
  medium  at least half disagree

Within a priority, model-labelled rows come before expert rows (harvested labels
were projected from a whole enforcement case onto single sentences, so they are
the noisiest), then short fragments, then the rest.

Two patterns are flagged in ``flags`` because they are known label hazards:

  fragment          content under 30 characters labelled non_compliant, often a
                    sentence cut from a case that was about something else
  hedge_only_pair   compliant minimal pair made only by adding a qualifier
                    (``technique: qualification_added``) that the systems still flag;
                    the rewrite may keep the unsubstantiated claim

Writes the column layout of ``harvest/eval_gold_review.csv`` plus local-model and
flag columns, so decisions apply with the existing tool:

  python3.11 ontology/tools/build_disagreement_queue.py RUN.json
  python3.11 ontology/tools/apply_eval_gold_decisions.py --csv ontology/examples/harvest/eval_disagreement_review.csv

The systems are advisory. Nothing here changes a label; a human fills
``human_decision`` (keep | drop | relabel_nc | relabel_c | quarantine).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ONTOLOGY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ONTOLOGY))

from examples.load_eval import load_eval_with_sources  # noqa: E402

OUT = ONTOLOGY / "examples" / "harvest" / "eval_disagreement_review.csv"

SYSTEMS = (
    ("matcher", "matcher_display"),
    ("local", "local_display"),
    ("gemini", "gemini_display"),
)

COLUMNS = [
    "priority",
    "error_type",
    "id",
    "source",
    "gold_label",
    "category_ids",
    "content_len",
    "matcher_viol",
    "content",
    "gemini_quality",
    "gemini_label_agree",
    "gemini_suggested_label",
    "gemini_reason",
    "human_decision",
    "human_notes",
    # Additions; ignored by apply_eval_gold_decisions.py.
    "labeled_by",
    "split",
    "systems_disagreeing",
    "matcher_display",
    "local_display",
    "local_rationale",
    "flags",
]

_TECHNIQUE_RE = re.compile(r"technique:\s*([a-z_]+)")
_FRAGMENT_CHARS = 30


def is_positive(status: Any) -> bool:
    return str(status or "").strip().upper() in {
        "NON_COMPLIANT",
        "LIKELY_REJECTED",
        "REVIEW_REQUIRED",
        "BORDERLINE",
    }


def flags_for(row: dict[str, Any], example: dict[str, Any]) -> list[str]:
    content = str(example.get("content") or "")
    out = []
    if row["label"] == "non_compliant" and len(content.strip()) < _FRAGMENT_CHARS:
        out.append("fragment")
    technique = _TECHNIQUE_RE.search(str(example.get("note") or ""))
    if row["label"] == "compliant" and technique and technique.group(1) == "qualification_added":
        out.append("hedge_only_pair")
    return out


def build_queue(rows: list[dict[str, Any]], examples: dict[str, dict]) -> list[dict[str, Any]]:
    queue = []
    for row in rows:
        if row.get("error") or row.get("label") not in {"compliant", "non_compliant"}:
            continue
        gold_positive = row["label"] == "non_compliant"
        scored = [name for name, field in SYSTEMS if row.get(field)]
        disagreeing = [
            name for name, field in SYSTEMS if row.get(field) and is_positive(row[field]) != gold_positive
        ]
        if len(scored) < 2 or len(disagreeing) * 2 < len(scored):
            continue
        example = examples.get(row["id"], {})
        content = str(example.get("content") or row.get("content_preview") or "")
        flags = flags_for(row, example)
        queue.append(
            {
                "priority": "high" if len(disagreeing) == len(scored) else "medium",
                "error_type": "FN" if gold_positive else "FP",
                "id": row["id"],
                "source": row.get("source") or "",
                "gold_label": row["label"],
                "category_ids": ",".join(example.get("category_ids") or row.get("category_ids") or []),
                "content_len": len(content),
                "matcher_viol": int(is_positive(row.get("matcher_display"))),
                "content": content,
                "gemini_quality": "",
                "gemini_label_agree": "" if not row.get("gemini_display") else
                ("no" if "gemini" in disagreeing else "yes"),
                "gemini_suggested_label": "",
                "gemini_reason": "",
                "human_decision": "",
                "human_notes": "",
                "labeled_by": example.get("labeled_by") or row.get("labeled_by") or "",
                "split": row.get("split") or example.get("split") or "",
                "systems_disagreeing": f"{len(disagreeing)}/{len(scored)} ({','.join(disagreeing)})",
                "matcher_display": row.get("matcher_display") or "",
                "local_display": row.get("local_display") or "",
                "local_rationale": row.get("summary") or "",
                "flags": ",".join(flags),
            }
        )

    def sort_key(item: dict[str, Any]) -> tuple:
        return (
            item["priority"] != "high",
            item["labeled_by"] == "expert",
            "fragment" not in item["flags"] and "hedge_only_pair" not in item["flags"],
            item["content_len"],
        )

    return sorted(queue, key=sort_key)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path, help="JSON written by scripts/eval_local_review.py")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--limit", type=int, default=0, help="Keep only the first N queued rows (0 = all)")
    args = parser.parse_args()

    rows = json.loads(args.run.read_text(encoding="utf-8")).get("rows") or []
    examples_list, _ = load_eval_with_sources(str(ONTOLOGY))
    examples = {e["id"]: e for e in examples_list}
    queue = build_queue(rows, examples)
    if args.limit:
        queue = queue[: args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(queue)

    by = Counter((q["priority"], q["error_type"]) for q in queue)
    flagged = Counter(flag for q in queue for flag in q["flags"].split(",") if flag)
    print(f"Scored rows: {len(rows)}  queued: {len(queue)}")
    for key in sorted(by):
        print(f"  {key[0]:<6} {key[1]}: {by[key]}")
    for flag, n in flagged.most_common():
        print(f"  flag {flag}: {n}")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
