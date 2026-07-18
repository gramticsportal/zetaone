#!/usr/bin/env python3
"""Build ontology/policy_timeline.yaml from the corpus + policy_versions sidecar.

Answers per clause: when introduced, when modified, what changed, why (if official).

Run:  python ontology/tools/build_policy_timeline.py
Writes: ontology/policy_timeline.yaml (regenerates the auto-seeded baseline).
Manual timeline entries in policy_timeline.yaml are preserved if marked manual: true.
"""
from __future__ import annotations

import glob
import os
from datetime import date

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "corpus")
PV_PATH = os.path.join(ROOT, "policy_versions.yaml")
OUT_PATH = os.path.join(ROOT, "policy_timeline.yaml")


def load(path: str):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def clauses_by_source() -> dict[str, list[dict]]:
    by_src: dict[str, list[dict]] = {}
    for path in sorted(glob.glob(os.path.join(CORPUS, "*.yaml"))):
        doc = load(path)
        for cl in doc.get("clauses", []):
            by_src.setdefault(cl["source_id"], []).append(cl)
    return by_src


def main() -> None:
    by_src = clauses_by_source()
    pv = load(PV_PATH)
    manual: dict[str, list] = {}
    if os.path.exists(OUT_PATH):
        existing = load(OUT_PATH)
        for entry in existing.get("timeline", []) or []:
            cid = entry.get("clause_id")
            manual_events = [
                e for e in (entry.get("events") or [])
                if e.get("manual")
            ]
            if manual_events:
                manual[cid] = manual_events

    timeline: list[dict] = []
    today = date.today().isoformat()

    for cl_list in by_src.values():
        for cl in sorted(cl_list, key=lambda c: c["id"]):
            cid = cl["id"]
            events: list[dict] = []

            eff = cl.get("effective_date")
            ver = cl.get("version", "")
            ev = cl.get("evidence") or {}
            events.append({
                "date": eff,
                "event_type": "introduced",
                "version": ver,
                "summary": (
                    f"Clause first ingested from official source "
                    f"({cl.get('source_id')}); effective_date/version from source page."
                ),
                "reason": None,
                "source_url": ev.get("source_url"),
                "section": ev.get("section"),
                "official": True,
                "corpus_note": "Auto-seeded from clause effective_date at ingestion.",
            })

            if cl.get("status") == "superseded" and cl.get("superseded_by"):
                events.append({
                    "date": cl.get("last_verified_at", eff),
                    "event_type": "superseded",
                    "version": ver,
                    "summary": f"Superseded by {cl['superseded_by']}.",
                    "reason": None,
                    "source_url": ev.get("source_url"),
                    "official": False,
                    "corpus_note": "Corpus lifecycle marker.",
                })

            # Source-level official change history -> modified events for all clauses
            sid = cl.get("source_id")
            for pol in pv.get("policies", []) or []:
                if pol.get("source_id") != sid:
                    continue
                for ch in pol.get("change_history", []) or []:
                    events.append({
                        "date": ch.get("date"),
                        "event_type": "modified",
                        "version": ch.get("version"),
                        "summary": ch.get("summary"),
                        "reason": ch.get("summary"),
                        "source_url": ch.get("url"),
                        "official": True,
                        "policy_title": pol.get("policy_title"),
                    })

            if cid in manual:
                events.extend(manual[cid])

            # Sort events by date string (coarse but stable)
            events.sort(key=lambda e: str(e.get("date") or ""))

            timeline.append({
                "clause_id": cid,
                "source_id": sid,
                "category_id": cl.get("category_id"),
                "current_version": ver,
                "current_status": cl.get("status", "active"),
                "events": events,
            })

    doc = {
        "schema_note": (
            "Policy diff timeline — SIDECAR (not part of frozen schema v1.0.0). "
            "Per-clause audit trail: introduced / modified / deprecated / superseded. "
            "Events with official: true cite published policy changes; auto-seeded "
            "introduced events use clause effective_date. Regenerate baseline with "
            "python ontology/tools/build_policy_timeline.py (preserves manual: true events)."
        ),
        "generated_at": today,
        "timeline": timeline,
    }
    with open(OUT_PATH, "w") as f:
        yaml.dump(doc, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    print(f"Wrote {len(timeline)} clause timelines -> {OUT_PATH}")


if __name__ == "__main__":
    main()
