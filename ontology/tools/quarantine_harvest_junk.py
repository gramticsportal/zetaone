#!/usr/bin/env python3
"""Move fragment / not-a-claim harvested rows (and their compliant twins) out of eval.

The quality audit labels every harvested row as assessable_claim, fragment, or
not_a_claim. Those last two are extraction noise: truncated spans and document
prose that no reviewer could rule on in isolation. Leaving them in the eval set
makes recall look worse than the matcher is, and deleting *only* the misses
would make recall look better than it is. Both sides of the label go, so the
metric stays honest.

Quarantined rows are written to examples/harvest/, not deleted. The loader does
not include them. Re-run after regenerating harvest/harvest_quality_audit.csv.

The not_a_claim bucket slightly over-calls product names that *are* the claim
(e.g. "Protect-A-Bed Bamboo Waterproof Mattress Protector"). Those stay in the
quarantine file and can be promoted back after a human pass.

Usage:
    python3.11 ontology/tools/quarantine_harvest_junk.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import yaml

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
EVAL = EXAMPLES / "eval"
HARVEST = EXAMPLES / "harvest"
AUDIT = HARVEST / "harvest_quality_audit.csv"
JUNK_LABELS = {"fragment", "not_a_claim"}


def dump(path: Path, examples: list[dict], preamble: str) -> None:
    path.write_text(
        preamble + yaml.safe_dump({"examples": examples}, sort_keys=False, allow_unicode=True, width=1000),
        encoding="utf-8",
    )


def main() -> int:
    if not AUDIT.exists():
        print(f"missing {AUDIT} — run audit_missed_violations.py first", file=sys.stderr)
        return 2

    junk_ids = {
        row["id"]
        for row in csv.DictReader(AUDIT.open())
        if row.get("label") in JUNK_LABELS
    }
    if not junk_ids:
        print("audit has no fragment/not_a_claim rows; nothing to do")
        return 0

    harvested = yaml.safe_load((EVAL / "eval_harvested.yaml").read_text(encoding="utf-8"))["examples"]
    keep_h = [e for e in harvested if e["id"] not in junk_ids]
    drop_h = [e for e in harvested if e["id"] in junk_ids]

    pairs = yaml.safe_load((EVAL / "eval_compliant_pairs.yaml").read_text(encoding="utf-8"))["examples"]
    keep_p, drop_p = [], []
    for e in pairs:
        source = e["id"].removesuffix("_compliant")
        (drop_p if source in junk_ids else keep_p).append(e)

    dump(
        EVAL / "eval_harvested.yaml",
        keep_h,
        "# Evaluation examples harvested verbatim from enforcement documents.\n"
        "# Denoised: fragment / not_a_claim rows moved to harvest/eval_harvested_quarantined.yaml\n"
        "# after harvest/harvest_quality_audit.csv. Re-run: python3.11 ontology/tools/quarantine_harvest_junk.py\n"
        f"# Total: {len(keep_h)} assessable  (quarantined {len(drop_h)})\n\n",
    )
    dump(
        HARVEST / "eval_harvested_quarantined.yaml",
        drop_h,
        "# Harvested rows the quality audit labelled fragment or not_a_claim.\n"
        "# Not loaded by load_eval.py. Promote back after human review if a row is a real claim.\n"
        f"# Total: {len(drop_h)}\n\n",
    )
    dump(
        EVAL / "eval_compliant_pairs.yaml",
        keep_p,
        "# Synthetic COMPLIANT minimal pairs for the harvested non-compliant rows.\n"
        "# Twins of quarantined harvested rows are held here out of the eval set.\n"
        f"# Total: {len(keep_p)} pairs  (quarantined {len(drop_p)})\n\n",
    )
    dump(
        HARVEST / "eval_compliant_pairs_quarantined.yaml",
        drop_p,
        "# Compliant twins of quarantined harvested rows. Not loaded.\n"
        f"# Total: {len(drop_p)}\n\n",
    )

    print(f"harvested: {len(harvested)} -> {len(keep_h)} keep, {len(drop_h)} quarantined")
    print(f"pairs:     {len(pairs)} -> {len(keep_p)} keep, {len(drop_p)} quarantined")
    return 0


if __name__ == "__main__":
    sys.exit(main())
