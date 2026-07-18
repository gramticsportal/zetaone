#!/usr/bin/env python3
"""Corpus coverage statistics — domain, platform, jurisdiction, canonical rule.

Run:  python ontology/benchmark/coverage.py
      python ontology/benchmark/coverage.py --json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from examples.load_eval import load_eval_examples  # noqa: E402


def load(path: str):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def collect_corpus():
    clauses: list[dict] = []
    sources: dict[str, dict] = {}
    rules: list[dict] = []
    for path in sorted(glob.glob(os.path.join(ROOT, "corpus", "*.yaml"))):
        doc = load(path)
        srcs = doc.get("sources") or ([doc["source"]] if "source" in doc else [])
        for s in srcs:
            sources[s["id"]] = s
        clauses.extend(doc.get("clauses", []))
        rules.extend(doc.get("rules", []))
    return clauses, sources, rules


def collect_mappings():
    mp = load(os.path.join(ROOT, "mappings.yaml"))
    canonicals: dict[str, dict] = {}
    for m in mp.get("mappings", []):
        canonicals[m["canonical_id"]] = m
    for r in collect_corpus()[2]:
        if r.get("canonical_id"):
            canonicals.setdefault(r["canonical_id"], {}).setdefault(
                "clause_ids", r.get("clause_ids", [])
            )
    return canonicals


def collect_precedents():
    prec: list[dict] = []
    prec_dir = os.path.join(ROOT, "precedents")
    if os.path.isdir(prec_dir):
        for path in sorted(glob.glob(os.path.join(prec_dir, "*.yaml"))):
            prec.extend(load(path).get("precedents", []) or [])
    return prec


def collect_examples():
    return load_eval_examples(ROOT)


def source_jurisdiction_map(sources: dict[str, dict]) -> dict[str, list]:
    return {sid: s.get("jurisdiction", []) for sid, s in sources.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Ontology corpus coverage stats")
    parser.add_argument("--json", action="store_true", help="Emit JSON only")
    args = parser.parse_args()

    categories = {c["id"] for c in load(os.path.join(ROOT, "categories.yaml"))["categories"]}
    clauses, sources, rules = collect_corpus()
    mappings = collect_mappings()
    precedents = collect_precedents()
    examples = collect_examples()
    jmap = source_jurisdiction_map(sources)

    by_category = Counter(c.get("category_id") for c in clauses)
    by_source = Counter(c.get("source_id") for c in clauses)
    by_jurisdiction: Counter = Counter()
    for c in clauses:
        for j in c.get("jurisdiction") or jmap.get(c.get("source_id"), []):
            by_jurisdiction[j] += 1

    platform_sources = [s for s in sources.values() if s.get("type") == "platform"]
    regulator_sources = [s for s in sources.values() if s.get("type") == "regulator"]

    canonical_sources: dict[str, set] = defaultdict(set)
    for cid, m in mappings.items():
        for clid in m.get("clause_ids") or []:
            canonical_sources[cid].add(clid.split(".", 1)[0])

    single_source_canonicals = [
        c for c, srcs in canonical_sources.items() if len(srcs) < 2
    ]
    cross_source_canonicals = [
        c for c, srcs in canonical_sources.items() if len(srcs) >= 2
    ]

    prec_by_outcome = Counter(p.get("outcome") for p in precedents)
    prec_by_category: Counter = Counter()
    for p in precedents:
        for cat in p.get("category_ids") or []:
            prec_by_category[cat] += 1

    cats_without_precedents = sorted(categories - set(prec_by_category.keys()))
    cats_with_clauses_no_precedents = sorted(
        set(by_category.keys()) - set(prec_by_category.keys())
    )

    ex_by_category: Counter = Counter()
    for e in examples:
        for cat in e.get("category_ids") or []:
            ex_by_category[cat] += 1

    report = {
        "totals": {
            "clauses": len(clauses),
            "sources": len(sources),
            "platform_sources": len(platform_sources),
            "regulator_sources": len(regulator_sources),
            "canonical_rules": len(canonical_sources),
            "cross_source_canonicals": len(cross_source_canonicals),
            "single_source_canonicals": len(single_source_canonicals),
            "eval_examples": len(examples),
            "precedents": len(precedents),
        },
        "clauses_by_category": dict(sorted(by_category.items())),
        "clauses_by_source": dict(sorted(by_source.items())),
        "clauses_by_jurisdiction": dict(sorted(by_jurisdiction.items())),
        "eval_examples_by_category": dict(sorted(ex_by_category.items())),
        "precedents_by_outcome": dict(sorted(prec_by_outcome.items())),
        "precedents_by_category": dict(sorted(prec_by_category.items())),
        "gaps": {
            "categories_without_precedents": cats_without_precedents,
            "categories_with_clauses_but_no_precedents": cats_with_clauses_no_precedents,
            "single_source_canonical_ids": sorted(single_source_canonicals),
        },
        "platform_source_ids": sorted(s["id"] for s in platform_sources),
        "regulator_source_ids": sorted(s["id"] for s in regulator_sources),
    }

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    t = report["totals"]
    print("=== Ontology Corpus Coverage ===")
    print(f"clauses: {t['clauses']}  sources: {t['sources']} "
          f"(platforms: {t['platform_sources']}, regulators: {t['regulator_sources']})")
    print(f"canonicals: {t['canonical_rules']} "
          f"(cross-source: {t['cross_source_canonicals']}, "
          f"single-source: {t['single_source_canonicals']})")
    print(f"eval_examples: {t['eval_examples']}  precedents: {t['precedents']}")
    print("\n--- Clauses by category ---")
    for cat, n in report["clauses_by_category"].items():
        ex = report["eval_examples_by_category"].get(cat, 0)
        pr = report["precedents_by_category"].get(cat, 0)
        print(f"  {cat:20s}  clauses={n:4d}  evals={ex:4d}  precedents={pr:3d}")
    print("\n--- Clauses by jurisdiction ---")
    for j, n in report["clauses_by_jurisdiction"].items():
        print(f"  {j:6s}  {n}")
    print("\n--- Gaps ---")
    print(f"  categories with clauses but no precedents: "
          f"{report['gaps']['categories_with_clauses_but_no_precedents']}")
    print(f"  single-source canonicals: {len(report['gaps']['single_source_canonical_ids'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
