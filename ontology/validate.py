#!/usr/bin/env python3
"""Validate the ZataOne ontology corpus: parse, referential integrity, and
completeness of evidence / applicability / last_reviewed_by fields.

Run from anywhere:  python ontology/validate.py
Exits non-zero if any ERROR is found. WARNINGs do not fail the build.
"""
from __future__ import annotations

import glob
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.abspath(__file__))

AUDIENCE = {"all", "under_13", "minors", "13+", "16+", "18+", "21+", "25+"}
REVIEW_ACTOR = {"human", "ai"}
EXAMPLE_LABEL = {"compliant", "non_compliant", "borderline"}
POLICY_STATUS = {"active", "deprecated", "superseded"}

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load(path: str):
    with open(path) as f:
        return yaml.safe_load(f)


def main() -> int:
    # ---- load ----------------------------------------------------------
    categories = {c["id"] for c in load(os.path.join(ROOT, "categories.yaml"))["categories"]}

    clause_ids: set[str] = set()
    clause_category: dict[str, str] = {}
    source_ids: set[str] = set()
    canonical_clause_refs: list[tuple[str, str, str]] = []  # (file, canonical, clause)

    corpus_files = sorted(glob.glob(os.path.join(ROOT, "corpus", "*.yaml")))
    for path in corpus_files:
        name = os.path.basename(path)
        doc = load(path)

        # source(s)
        srcs = doc.get("sources") or ([doc["source"]] if "source" in doc else [])
        for s in srcs:
            source_ids.add(s["id"])

        for cl in doc.get("clauses", []):
            cid = cl["id"]
            if cid in clause_ids:
                err(f"{name}: duplicate clause id {cid}")
            clause_ids.add(cid)
            clause_category[cid] = cl.get("category_id", "")

            if cl.get("category_id") not in categories:
                err(f"{name}: clause {cid} unknown category {cl.get('category_id')}")
            if cl.get("source_id") not in source_ids:
                err(f"{name}: clause {cid} references unknown source {cl.get('source_id')}")

            # evidence completeness
            ev = cl.get("evidence") or {}
            for key in ("quote", "source_url", "section", "retrieved_at"):
                if not ev.get(key):
                    err(f"{name}: clause {cid} missing evidence.{key}")

            # last_reviewed_by
            lrb = cl.get("last_reviewed_by")
            if lrb not in REVIEW_ACTOR:
                err(f"{name}: clause {cid} bad last_reviewed_by {lrb!r}")

            # applicability (optional, but validate when present)
            app = cl.get("applicability")
            if app is None:
                warn(f"{name}: clause {cid} has no applicability block")
            else:
                for a in app.get("audience", []) or []:
                    if a not in AUDIENCE:
                        err(f"{name}: clause {cid} bad audience {a!r}")
                for ind in app.get("industries", []) or []:
                    if ind not in categories and ind != "all":
                        err(f"{name}: clause {cid} bad industry {ind!r}")

        # rules reference existing clauses
        for r in doc.get("rules", []):
            for cid in r.get("clause_ids", []):
                if cid not in clause_ids and cid not in [c["id"] for c in doc.get("clauses", [])]:
                    # may be defined later in same file; collect and check after
                    pass

    # second pass: rule clause refs across full clause set
    for path in corpus_files:
        name = os.path.basename(path)
        doc = load(path)
        for r in doc.get("rules", []):
            for cid in r.get("clause_ids", []):
                if cid not in clause_ids:
                    err(f"{name}: rule {r.get('id')} references unknown clause {cid}")

    # ---- mappings ------------------------------------------------------
    mp = load(os.path.join(ROOT, "mappings.yaml"))
    for m in mp.get("mappings", []):
        cids = m.get("clause_ids", [])
        for cid in cids:
            if cid not in clause_ids:
                err(f"mappings.yaml: canonical {m['canonical_id']} unknown clause {cid}")
        srcs_in_map = {clause_prefix_source(cid) for cid in cids}
        if len(srcs_in_map) < 2:
            warn(f"mappings.yaml: canonical {m['canonical_id']} is single-source "
                 f"({srcs_in_map}); fine if intentional.")

    # ---- examples ------------------------------------------------------
    ex = load(os.path.join(ROOT, "examples", "eval_seed.yaml"))
    counts: dict[str, int] = {}
    seen_ids: set[str] = set()
    for e in ex.get("examples", []):
        eid = e["id"]
        if eid in seen_ids:
            err(f"eval_seed.yaml: duplicate example id {eid}")
        seen_ids.add(eid)
        if e.get("label") not in EXAMPLE_LABEL:
            err(f"eval_seed.yaml: {eid} bad label {e.get('label')}")
        counts[e.get("label", "?")] = counts.get(e.get("label", "?"), 0) + 1
        for cat in e.get("category_ids", []):
            if cat not in categories:
                err(f"eval_seed.yaml: {eid} unknown category {cat}")
        for cid in e.get("violated_clause_ids", []) or []:
            if cid not in clause_ids:
                err(f"eval_seed.yaml: {eid} unknown violated clause {cid}")
        if e.get("label") == "compliant" and (e.get("violated_clause_ids") or []):
            err(f"eval_seed.yaml: {eid} compliant but has violated_clause_ids")
        if e.get("label") == "non_compliant" and not (e.get("violated_clause_ids") or []):
            err(f"eval_seed.yaml: {eid} non_compliant but no violated_clause_ids")

    # ---- policy_versions sidecar (optional; NOT part of frozen schema) -
    pv_path = os.path.join(ROOT, "policy_versions.yaml")
    pv_count = 0
    if os.path.exists(pv_path):
        pv = load(pv_path) or {}
        seen_pv: set[str] = set()
        for p in pv.get("policies", []) or []:
            pv_count += 1
            sid = p.get("source_id")
            if sid not in source_ids:
                err(f"policy_versions.yaml: entry references unknown source {sid!r}")
            if sid in seen_pv:
                warn(f"policy_versions.yaml: duplicate source entry {sid!r} (ok if multiple policies)")
            seen_pv.add(sid)
            st = p.get("status")
            if st not in POLICY_STATUS:
                err(f"policy_versions.yaml: {sid} bad status {st!r}")
            if st == "superseded" and not p.get("superseded_by"):
                warn(f"policy_versions.yaml: {sid} superseded but no superseded_by")
            for ch in p.get("change_history", []) or []:
                if not ch.get("date"):
                    err(f"policy_versions.yaml: {sid} change_history entry missing date")

    # ---- report --------------------------------------------------------
    print(f"clauses: {len(clause_ids)}  sources: {len(source_ids)}  "
          f"examples: {len(seen_ids)} {counts}  policy_versions: {pv_count}")
    for w in warnings:
        print(f"WARN  {w}")
    if errors:
        for e in errors:
            print(f"ERROR {e}")
        print(f"\nFAILED with {len(errors)} error(s).")
        return 1
    print("\nOK — corpus is valid.")
    return 0


def clause_prefix_source(cid: str) -> str:
    """Map a clause id to its source family by prefix (meta./google./tiktok./
    linkedin./ftc./fda./sec./finra./cfpb.)."""
    return cid.split(".", 1)[0]


if __name__ == "__main__":
    sys.exit(main())
