#!/usr/bin/env python3
"""Measure the advisory semantic channel on held-out compliant pairs.

The lexical matcher is the only thing that can block. This script asks a narrower
question: of the violations the lexical layer misses, how many would a MiniLM
nearest-neighbour over *dev-split* harvested copy recover, and at what false-positive
rate on their lawful twins?

Index is built from the dev half only, so the test numbers are not self-similarity
against the same row. Thresholds are swept, not tuned on test.

Usage:
    python3.11 ontology/tools/eval_semantic_channel.py --split test
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ONTOLOGY.parent / "src"))

from zataone.extractors.semantic_text_extractor import (  # noqa: E402
    _CATEGORY_TO_REGULATION,
    SemanticTextExtractor,
)
from zataone.policy_engine.hybrid.lexical import match_lexical  # noqa: E402
from zataone.policy_engine.hybrid.pack_loader import load_pattern_packs  # noqa: E402


def split_of(example_id: str) -> str:
    digest = hashlib.sha1(example_id.encode()).hexdigest()
    return "dev" if int(digest[:8], 16) % 2 == 0 else "test"


def load_pairs() -> list[tuple[dict, dict]]:
    examples = ONTOLOGY / "examples"
    bad = {
        e["id"]: e
        for e in yaml.safe_load((examples / "eval_harvested.yaml").read_text()).get("examples", [])
    }
    good = yaml.safe_load((examples / "eval_compliant_pairs.yaml").read_text()).get("examples", [])
    return [
        (bad[g["id"].removesuffix("_compliant")], g)
        for g in good
        if g["id"].removesuffix("_compliant") in bad
    ]


def exemplars_from(rows: list[dict], max_per: int = 80) -> dict[str, list[str]]:
    buckets: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        text = (row.get("content") or "").strip()
        if len(text) < 15:
            continue
        for cat in row.get("category_ids") or []:
            reg = _CATEGORY_TO_REGULATION.get(cat)
            if reg:
                buckets[reg].append(text)
    return {reg: sorted(set(texts), key=len, reverse=True)[:max_per] for reg, texts in buckets.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--split", default="test", choices=["dev", "test"])
    args = parser.parse_args()

    packs = list(load_pattern_packs().values())
    pairs = load_pairs()
    index_rows = [b for b, _ in pairs if split_of(b["id"]) != args.split]
    eval_pairs = [(b, g) for b, g in pairs if split_of(b["id"]) == args.split]
    exemplars = exemplars_from(index_rows)
    print(
        f"split={args.split}  eval_pairs={len(eval_pairs)}  "
        f"index_rows={len(index_rows)}  exemplars="
        + ", ".join(f"{k}={len(v)}" for k, v in sorted(exemplars.items()))
    )

    ext = SemanticTextExtractor(similarity_threshold=0.0, exemplars=exemplars)
    encoder = ext._encoder or __import__(
        "zataone.extractors.semantic_text_extractor", fromlist=["_load_encoder"]
    )._load_encoder(ext._model_name)
    if encoder is None:
        print("MiniLM failed to load — cannot score the semantic channel.", file=sys.stderr)
        return 2
    ext._encoder = encoder

    def lexical(text: str) -> bool:
        return any(match_lexical(text, p) for p in packs)

    def semantic_score(text: str) -> float:
        signals = ext.extract(SimpleNamespace(type="text", content=text))
        return max((s.confidence for s in signals), default=0.0)

    print("scoring…", flush=True)
    rows = []
    for bad, good in eval_pairs:
        rows.append(
            {
                "lex_bad": lexical(bad["content"]),
                "lex_good": lexical(good["content"]),
                "sem_bad": semantic_score(bad["content"]),
                "sem_good": semantic_score(good["content"]),
            }
        )

    n = len(rows)
    lex_tp = sum(1 for r in rows if r["lex_bad"])
    lex_fp = sum(1 for r in rows if r["lex_good"])
    misses = [r for r in rows if not r["lex_bad"]]
    print(f"\nlexical only: recall={lex_tp / n:.1%}  FP-rate={lex_fp / n:.1%}  misses={len(misses)}")
    print("semantic on those misses (dev-index, held-out eval):")
    print(f"{'thr':>6}  recover_miss  FP_on_twin  combined_recall  combined_FP")
    for thr in (0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70):
        recovered = sum(1 for r in misses if r["sem_bad"] >= thr)
        fp_twin = sum(1 for r in misses if r["sem_good"] >= thr)
        comb_tp = sum(1 for r in rows if r["lex_bad"] or r["sem_bad"] >= thr)
        comb_fp = sum(1 for r in rows if r["lex_good"] or r["sem_good"] >= thr)
        print(
            f"{thr:6.2f}  {recovered / max(1, len(misses)):11.1%}  "
            f"{fp_twin / max(1, len(misses)):10.1%}  {comb_tp / n:15.1%}  {comb_fp / n:11.1%}"
        )
    closer = sum(1 for r in misses if r["sem_bad"] > r["sem_good"])
    print(f"\nmissed violation scores strictly above its own twin: {closer / max(1, len(misses)):.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
