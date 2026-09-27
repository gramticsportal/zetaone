#!/usr/bin/env python3
"""Validate ontology/examples/annotations/annotations.yaml against the eval corpus.

Checks every annotation references a real example, uses known enum values and real
dates, and that each evidence span is an exact substring of the example's content
(a span that does not appear in the ad cannot be used to train or score span finding).

  python3.11 ontology/tools/validate_annotations.py
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ONTOLOGY))

from examples.load_eval import load_eval_with_sources  # noqa: E402

PATH = ONTOLOGY / "examples" / "annotations" / "annotations.yaml"

ENUMS = {
    "platform": {"meta", "google", "tiktok", "amazon", "youtube", "x", "linkedin", "snap", "other"},
    "platform_decision": {"approved", "rejected", "restricted", "not_submitted"},
    "decision_source": {"human_review", "appeal", "platform_feedback"},
    "severity": {"low", "medium", "high"},
}
DATES = ("annotated_on", "policy_as_of")
KNOWN = {"example_id", "annotator", "evidence_spans", "note", *ENUMS, *DATES}


def validate(annotations: list[dict], examples: dict[str, dict]) -> list[str]:
    errors = []
    for i, a in enumerate(annotations):
        where = f"annotation {i} ({a.get('example_id')})"
        example = examples.get(str(a.get("example_id")))
        if example is None:
            errors.append(f"{where}: unknown example_id")
            continue
        if not str(a.get("annotator") or "").strip():
            errors.append(f"{where}: annotator is required")
        for key in sorted(set(a) - KNOWN):
            errors.append(f"{where}: unknown field {key!r}")
        for key, allowed in ENUMS.items():
            if key in a and a[key] not in allowed:
                errors.append(f"{where}: {key}={a[key]!r} not in {sorted(allowed)}")
        for key in DATES:
            if key in a:
                try:
                    date.fromisoformat(str(a[key]))
                except ValueError:
                    errors.append(f"{where}: {key}={a[key]!r} is not YYYY-MM-DD")
        content = str(example.get("content") or "")
        for span in a.get("evidence_spans") or []:
            if str(span) not in content:
                errors.append(f"{where}: evidence span not found in content: {span!r}")
        if a.get("evidence_spans") and example.get("label") == "compliant":
            errors.append(f"{where}: evidence spans on a compliant example")
    return errors


def main() -> int:
    doc = yaml.safe_load(PATH.read_text(encoding="utf-8")) or {}
    annotations = list(doc.get("annotations") or [])
    examples_list, _ = load_eval_with_sources(str(ONTOLOGY))
    examples = {e["id"]: e for e in examples_list}
    errors = validate(annotations, examples)
    for e in errors:
        print(f"ERROR {e}")
    platforms = Counter(a.get("platform") or "(none)" for a in annotations)
    print(
        f"{len(annotations)} annotations on {len({a.get('example_id') for a in annotations})} examples; "
        f"platforms {dict(platforms)}; {len(errors)} errors"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
