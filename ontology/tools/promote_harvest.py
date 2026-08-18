#!/usr/bin/env python3
"""Promote reviewed harvest candidates into ontology/examples/eval_harvested.yaml.

The pipeline is: harvest_enforcement_ads.py (recall) -> classify_harvest_candidates.py
(triage) -> a human ticking the keep? column of harvest_curated.csv -> this tool.

Provenance is the reason this exists. eval_precedents.yaml holds hand-written
reconstructions of what an ad probably said; these rows are the advertiser's actual
words, lifted from a complaint or consent order, and each one keeps a pointer back to
the PDF and page it came from so any label can be re-checked at the source.

labeled_by records how much a row has been vetted, using the enum the schema already
defines:
  expert - a human ticked keep? in the CSV
  model  - Gemini triage only, admitted via --accept-llm, still needs a human

Rows are dropped rather than guessed at when a clause, category or precedent does not
resolve, so the file always satisfies ontology/validate.py.

Usage:
    python3.11 ontology/tools/promote_harvest.py --dry-run
    python3.11 ontology/tools/promote_harvest.py                  # human-ticked rows only
    python3.11 ontology/tools/promote_harvest.py --accept-llm      # + untriaged model rows
"""

from __future__ import annotations

import argparse
import csv
import glob
import re
import sys
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
EXAMPLES = ONTOLOGY / "examples"

KEEP_VALUES = {"y", "yes", "1", "x", "keep", "true", "t"}
REJECT_VALUES = {"n", "no", "0", "drop", "false", "f", "reject"}

# Existing eval files to dedupe against, so a promoted row never collides with a
# synthetic seed or an earlier reconstruction of the same campaign.
EXISTING_EVAL = ("eval_seed.yaml", "eval_seed_clean.yaml", "eval_precedents.yaml")


def normalize(text: str) -> str:
    """Fold to a comparison key so near-identical copy collapses to one row."""
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def load_ontology() -> tuple[set[str], set[str], dict[str, dict]]:
    clause_ids: set[str] = set()
    for path in glob.glob(str(ONTOLOGY / "corpus" / "*.yaml")):
        doc = yaml.safe_load(Path(path).read_text()) or {}
        for clause in doc.get("clauses", []) or []:
            if clause.get("id"):
                clause_ids.add(clause["id"])

    categories: set[str] = set()
    cat_doc = yaml.safe_load((ONTOLOGY / "categories.yaml").read_text()) or {}
    for cat in cat_doc.get("categories", []) or []:
        if cat.get("id"):
            categories.add(cat["id"])

    precedents: dict[str, dict] = {}
    for path in glob.glob(str(ONTOLOGY / "precedents" / "*.yaml")):
        doc = yaml.safe_load(Path(path).read_text()) or {}
        for prec in doc.get("precedents", []) or []:
            if prec.get("precedent_id"):
                precedents[prec["precedent_id"]] = prec
    return clause_ids, categories, precedents


def load_existing_content() -> set[str]:
    seen: set[str] = set()
    for name in EXISTING_EVAL:
        path = EXAMPLES / name
        if not path.exists():
            continue
        doc = yaml.safe_load(path.read_text()) or {}
        for ex in doc.get("examples", []) or []:
            if ex.get("content"):
                seen.add(normalize(ex["content"]))
    return seen


def read_decisions(path: Path) -> tuple[set[str], set[str]]:
    """Return (confirmed, rejected) candidate ids from the human-edited CSV."""
    confirmed: set[str] = set()
    rejected: set[str] = set()
    if not path.exists():
        return confirmed, rejected
    with open(path, newline="") as fh:
        for row in csv.DictReader(fh):
            mark = (row.get("keep?") or "").strip().lower()
            cid = (row.get("candidate_id") or "").strip()
            if not cid or not mark:
                continue
            if mark in KEEP_VALUES:
                confirmed.add(cid)
            elif mark in REJECT_VALUES:
                rejected.add(cid)
    return confirmed, rejected


def example_id(row: dict) -> str:
    """Stable id derived from the precedent and the candidate's harvest number.

    Keyed off the candidate number rather than a running counter so that un-ticking one
    row does not renumber every row after it and silently break result comparisons.
    """
    prec_slug = re.sub(r"^prec\.", "", row["precedent_id"]).replace(".", "_")
    prec_slug = re.sub(r"[^a-z0-9_]", "", prec_slug.lower())
    num = re.sub(r"[^0-9]", "", row["candidate_id"]) or "0"
    return f"harv_ev_{prec_slug}_{num}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--curated",
        nargs="+",
        default=[str(EXAMPLES / "harvest_curated.yaml"), str(EXAMPLES / "nad_curated.yaml")],
        help="one or more classified harvest files; rows are merged and de-duplicated",
    )
    parser.add_argument(
        "--decisions",
        nargs="*",
        default=[str(EXAMPLES / "harvest_curated.csv"), str(EXAMPLES / "nad_curated.csv")],
        help="matching review CSVs; a keep?/reject in any of them applies",
    )
    parser.add_argument("--out", default=str(EXAMPLES / "eval_harvested.yaml"))
    parser.add_argument(
        "--accept-llm",
        action="store_true",
        help="also promote un-reviewed Gemini keepers, marked labeled_by: model",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=4,
        help="drop snippets shorter than this; a 2-word fragment is not a usable eval item",
    )
    parser.add_argument("--split", default="test", choices=["train", "dev", "test"])
    parser.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = parser.parse_args()

    clause_ids, categories, precedents = load_ontology()
    existing = load_existing_content()

    # The FTC and BBB harvests are the same kind of evidence from different bodies, so
    # they belong in one file. Merging here rather than emitting two eval files keeps
    # example ids stable, since each id is keyed to its own precedent and candidate.
    rows: list[dict] = []
    for path in args.curated:
        if not Path(path).exists():
            print(f"  (skipping absent {path})")
            continue
        chunk = yaml.safe_load(Path(path).read_text())["candidates"]
        print(f"  {len(chunk):5d} rows from {Path(path).name}")
        rows.extend(chunk)

    confirmed: set[str] = set()
    rejected: set[str] = set()
    for path in args.decisions:
        keep, drop = read_decisions(Path(path))
        confirmed |= keep
        rejected |= drop

    print(f"harvest rows: {len(rows)}")
    print(f"human decisions in CSV: keep={len(confirmed)} reject={len(rejected)}")
    if not confirmed and not args.accept_llm:
        print(
            "\nNothing ticked keep? yet, so there is nothing to promote.\n"
            f"Fill the keep? column in {', '.join(args.decisions)}, or pass --accept-llm to\n"
            "admit Gemini's keepers as labeled_by: model in the meantime."
        )
        return 0

    examples: list[dict] = []
    drops: dict[str, int] = {}
    seen_ids: set[str] = set()
    seen_content = set(existing)

    def drop(reason: str) -> None:
        drops[reason] = drops.get(reason, 0) + 1

    for row in rows:
        cid = row["candidate_id"]
        is_confirmed = cid in confirmed
        llm_keeper = (
            row.get("llm_label") == "ad_copy"
            and row.get("llm_supports_violation") in ("yes", "unclear")
        )

        if cid in rejected:
            drop("rejected by human")
            continue
        if is_confirmed:
            labeled_by = "expert"
        elif args.accept_llm and llm_keeper:
            labeled_by = "model"
        else:
            drop("not selected")
            continue

        content = " ".join((row.get("content") or "").split())
        if len(content.split()) < args.min_words:
            drop(f"shorter than {args.min_words} words")
            continue

        key = normalize(content)
        if not key:
            drop("empty after normalization")
            continue
        if key in seen_content:
            drop("duplicate content")
            continue

        prec = precedents.get(row["precedent_id"])
        if not prec:
            drop("unknown precedent")
            continue

        clauses = [c for c in (row.get("violated_clause_ids") or []) if c in clause_ids]
        if not clauses:
            drop("no resolvable violated clause")
            continue
        cats = [c for c in (row.get("category_ids") or []) if c in categories]
        if not cats:
            drop("no resolvable category")
            continue

        eid = example_id(row)
        if eid in seen_ids:
            drop("duplicate example id")
            continue

        seen_ids.add(eid)
        seen_content.add(key)
        page = row.get("document_page")
        examples.append(
            {
                "id": eid,
                "content": content,
                "modality": row.get("modality", "text"),
                "label": "non_compliant",
                "category_ids": cats,
                "violated_clause_ids": clauses,
                "jurisdiction": prec.get("jurisdiction", "US"),
                "labeled_by": labeled_by,
                "split": args.split,
                "note": (
                    f"derived_from: {row['precedent_id']}; verbatim from "
                    f"{row.get('document_url')} p{page}; candidate: {cid}"
                ),
            }
        )

    by_quality: dict[str, int] = {}
    for ex in examples:
        by_quality[ex["labeled_by"]] = by_quality.get(ex["labeled_by"], 0) + 1

    print(f"\npromoted: {len(examples)}")
    for k, v in sorted(by_quality.items()):
        print(f"  labeled_by {k}: {v}")
    print("\ndropped:")
    for reason, count in sorted(drops.items(), key=lambda kv: -kv[1]):
        print(f"  {count:5d}  {reason}")

    if args.dry_run:
        print("\ndry run, nothing written")
        return 0

    expert = by_quality.get("expert", 0)
    preamble = (
        "# Evaluation examples harvested verbatim from enforcement documents.\n"
        "#\n"
        "# Unlike eval_precedents.yaml (hand-written reconstructions), every row here is the\n"
        "# advertiser's actual published wording, quoted in an agency complaint or consent\n"
        "# order. The note field records the source PDF and page so labels stay checkable.\n"
        "#\n"
        "# labeled_by: expert = a human confirmed it; model = Gemini triage, still unreviewed.\n"
        "# This file is only loaded when ZATAONE_EVAL_INCLUDE_HARVESTED=1, so it cannot move\n"
        "# existing benchmark numbers by accident.\n"
        "#\n"
        "# Regenerate: python3.11 ontology/tools/promote_harvest.py [--accept-llm]\n"
        f"# Total: {len(examples)} examples ({expert} expert-confirmed, "
        f"{by_quality.get('model', 0)} model-triaged)\n"
    )
    body = yaml.dump({"examples": examples}, sort_keys=False, allow_unicode=True, width=1000)
    Path(args.out).write_text(preamble + "\n" + body)
    print(f"\nwrote {args.out}")
    if not expert:
        print(
            "\nNote: no rows are human-confirmed yet. Keep "
            "ZATAONE_EVAL_INCLUDE_HARVESTED unset for gold-standard runs."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
