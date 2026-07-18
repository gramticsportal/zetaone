#!/usr/bin/env python3
"""Simple keyword retrieval benchmark against ontology corpus clauses.

Uses token overlap scoring (lightweight baseline before embedding retrieval).
Run:  python ontology/benchmark/run_retrieval_tests.py
"""
from __future__ import annotations

import glob
import os
import re
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path: str):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def load_clauses() -> list[dict]:
    clauses: list[dict] = []
    for path in sorted(glob.glob(os.path.join(ROOT, "corpus", "*.yaml"))):
        doc = load(path)
        for cl in doc.get("clauses", []):
            rules = doc.get("rules", [])
            canon = None
            for r in rules:
                if cl["id"] in (r.get("clause_ids") or []):
                    canon = r.get("canonical_id")
                    break
            clauses.append({
                "id": cl["id"],
                "category_id": cl.get("category_id"),
                "canonical_id": canon,
                "text": cl.get("text", ""),
                "tokens": tokenize(cl.get("text", "") + " " + cl["id"]),
            })
    return clauses


def retrieve(query: str, clauses: list[dict], top_k: int = 10) -> list[dict]:
    q = tokenize(query)
    scored = []
    for cl in clauses:
        overlap = len(q & cl["tokens"])
        if overlap:
            scored.append((overlap, cl))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [c for _, c in scored[:top_k]]


def main() -> int:
    tests_path = os.path.join(ROOT, "benchmark", "retrieval_tests.yaml")
    tests_doc = load(tests_path)
    clauses = load_clauses()
    tests = tests_doc.get("tests", []) or []

    passed = 0
    failed = 0
    for t in tests:
        tid = t["id"]
        query = t["query"]
        top_k = t.get("top_k", 10)
        hits = retrieve(query, clauses, top_k=top_k)
        hit_ids = {h["id"] for h in hits}
        hit_cats = {h["category_id"] for h in hits}
        hit_canons = {h["canonical_id"] for h in hits if h["canonical_id"]}

        ok = True
        missing: list[str] = []
        for cid in t.get("must_include_clause_ids") or []:
            if cid not in hit_ids:
                ok = False
                missing.append(f"clause:{cid}")
        for cat in t.get("must_include_category_ids") or []:
            if cat not in hit_cats:
                ok = False
                missing.append(f"category:{cat}")
        for can in t.get("must_include_canonical_ids") or []:
            if can not in hit_canons:
                ok = False
                missing.append(f"canonical:{can}")

        if ok:
            passed += 1
            print(f"PASS  {tid}")
        else:
            failed += 1
            print(f"FAIL  {tid}  missing={missing}  top={list(hit_ids)[:5]}")

    print(f"\n{passed}/{len(tests)} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
