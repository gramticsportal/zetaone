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
TIMELINE_EVENT = {"introduced", "modified", "deprecated", "superseded"}
PRECEDENT_OUTCOME = {
    "warning_letter", "consent_order", "settlement", "civil_penalty", "fine",
    "suspension", "court_order", "injunction", "marketing_denial", "refund",
    "no_action", "guidance",
}
PRECEDENT_STATUS = {"final", "proposed", "on_appeal", "rescinded", "vacated"}
PRECEDENT_CONFIDENCE = {"verified", "unverified"}

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
    canonical_ids: set[str] = set()
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
            if r.get("canonical_id"):
                canonical_ids.add(r["canonical_id"])
            for cid in r.get("clause_ids", []):
                if cid not in clause_ids:
                    err(f"{name}: rule {r.get('id')} references unknown clause {cid}")

    # ---- mappings ------------------------------------------------------
    mp = load(os.path.join(ROOT, "mappings.yaml"))
    for m in mp.get("mappings", []):
        canonical_ids.add(m["canonical_id"])
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

    # ---- precedents layer (Phase 2 sidecar; NOT part of frozen schema) -
    # Links enforcement actions to the policy corpus:
    #   Policy -> Canonical Rule -> Precedent -> Evidence -> Verdict.
    prec_dir = os.path.join(ROOT, "precedents")
    prec_count = 0
    if os.path.isdir(prec_dir):
        seen_prec: set[str] = set()
        for path in sorted(glob.glob(os.path.join(prec_dir, "*.yaml"))):
            name = os.path.basename(path)
            doc = load(path) or {}
            for p in doc.get("precedents", []) or []:
                prec_count += 1
                pid = p.get("precedent_id")
                if not pid:
                    err(f"{name}: precedent missing precedent_id")
                    continue
                if pid in seen_prec:
                    err(f"{name}: duplicate precedent_id {pid}")
                seen_prec.add(pid)

                # required descriptive fields
                for key in (
                    "source",
                    "source_url",
                    "date",
                    "title",
                    "summary",
                    "outcome",
                    "why_this_matters",
                    "confidence",
                    "last_verified_at",
                ):
                    if not p.get(key):
                        err(f"{name}: precedent {pid} missing {key}")

                kws = p.get("retrieval_keywords") or []
                if not kws:
                    err(f"{name}: precedent {pid} missing retrieval_keywords")
                conf = p.get("confidence")
                if conf not in PRECEDENT_CONFIDENCE:
                    err(f"{name}: precedent {pid} bad confidence {conf!r}")

                out = p.get("outcome")
                if out is not None and out not in PRECEDENT_OUTCOME:
                    err(f"{name}: precedent {pid} bad outcome {out!r}")
                st = p.get("status")
                if st is not None and st not in PRECEDENT_STATUS:
                    err(f"{name}: precedent {pid} bad status {st!r}")

                # referential integrity into the policy corpus
                for cid in p.get("violated_clause_ids", []) or []:
                    if cid not in clause_ids:
                        err(f"{name}: precedent {pid} unknown violated clause {cid}")
                for can in p.get("canonical_ids", []) or []:
                    if can not in canonical_ids:
                        err(f"{name}: precedent {pid} unknown canonical_id {can}")
                for cat in p.get("category_ids", []) or []:
                    if cat not in categories:
                        err(f"{name}: precedent {pid} unknown category {cat}")
                if not (p.get("violated_clause_ids") or p.get("canonical_ids")):
                    warn(f"{name}: precedent {pid} links to no clause or canonical")

                # evidence/citations: at least one quote+source_url pair
                ev = p.get("evidence", []) or []
                if not ev:
                    err(f"{name}: precedent {pid} missing evidence/citations")
                for i, e in enumerate(ev):
                    if not e.get("quote") or not e.get("source_url"):
                        err(f"{name}: precedent {pid} evidence[{i}] needs quote + source_url")

    # ---- policy_timeline sidecar (optional; NOT part of frozen schema) ----
    tl_path = os.path.join(ROOT, "policy_timeline.yaml")
    tl_count = 0
    if os.path.exists(tl_path):
        tl = load(tl_path) or {}
        seen_tl: set[str] = set()
        for entry in tl.get("timeline", []) or []:
            tl_count += 1
            cid = entry.get("clause_id")
            if not cid:
                err("policy_timeline.yaml: entry missing clause_id")
                continue
            if cid in seen_tl:
                err(f"policy_timeline.yaml: duplicate clause_id {cid}")
            seen_tl.add(cid)
            if cid not in clause_ids:
                err(f"policy_timeline.yaml: unknown clause_id {cid}")
            for ev in entry.get("events", []) or []:
                if ev.get("event_type") not in TIMELINE_EVENT:
                    err(f"policy_timeline.yaml: {cid} bad event_type {ev.get('event_type')!r}")
                if not ev.get("date"):
                    err(f"policy_timeline.yaml: {cid} event missing date")
                if not ev.get("summary"):
                    err(f"policy_timeline.yaml: {cid} event missing summary")

    # ---- report --------------------------------------------------------
    print(f"clauses: {len(clause_ids)}  sources: {len(source_ids)}  "
          f"canonicals: {len(canonical_ids)}  examples: {len(seen_ids)} {counts}  "
          f"policy_versions: {pv_count}  precedents: {prec_count}  "
          f"policy_timeline: {tl_count}")
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
