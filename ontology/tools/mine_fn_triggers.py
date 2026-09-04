#!/usr/bin/env python3
"""Mine pack trigger candidates from matcher false negatives (dry-run by default).

Step 1 of matcher improvement: most pair/harvest misses are \"no trigger matched\".
This finds n-grams that appear in FN (gold NC, matcher clear) more than in compliant
copy, grouped by gold category, and writes a review CSV — it does **not** rewrite packs.

Usage:
  PYTHONPATH=src python3.11 ontology/tools/mine_fn_triggers.py
  PYTHONPATH=src python3.11 ontology/tools/mine_fn_triggers.py --min-fn 3 --top 40

Review ontology/patterns/candidates_fn_review.csv, then hand-add strong phrases/regex
into ontology/patterns/by_category/<cat>.yaml (approved packs only).
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "ontology"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ONTOLOGY))

OUT = ONTOLOGY / "patterns" / "candidates_fn_review.csv"
TOKEN_RE = re.compile(r"[a-z0-9$%][a-z0-9$%'’-]*")
STOP = {
    "the", "and", "your", "you", "our", "is", "are", "a", "an", "to", "of", "in", "on",
    "for", "with", "at", "by", "it", "we", "us", "that", "this", "be", "as", "or", "from",
    "will", "can", "any", "all", "more", "get", "now", "new", "up", "out", "so", "if",
    "has", "have", "was", "were", "not", "no", "do", "does", "just", "only", "than",
    "when", "what", "who", "how", "their", "its", "his", "her", "them", "they", "he",
    "she", "i", "my", "me", "one", "two", "s", "t", "also", "into", "over", "after",
}


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall((text or "").lower())


def ngrams(text: str, n_max: int = 3) -> list[str]:
    toks = tokens(text)
    out: list[str] = []
    for n in range(1, n_max + 1):
        for i in range(len(toks) - n + 1):
            gram = " ".join(toks[i : i + n])
            parts = gram.split()
            if all(p in STOP for p in parts):
                continue
            if n == 1 and (parts[0] in STOP or len(parts[0]) < 4):
                continue
            out.append(gram)
    return out


def log_odds(fn: int, comp: int, n_fn: int, n_comp: int, a: float = 0.01) -> float:
    """Monroe-style informative prior; higher = more FN-associated."""
    p1 = (fn + a) / (n_fn + a * 2)
    p0 = (comp + a) / (n_comp + a * 2)
    return math.log(p1) - math.log(p0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-fn", type=int, default=3, help="min FN occurrences")
    parser.add_argument("--top", type=int, default=30, help="top candidates per category")
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()

    os.environ.setdefault("ZATAONE_HYBRID_ENGINE", "1")
    os.environ.setdefault("ZATAONE_HYBRID_NLP", "0")

    from examples.load_eval import load_eval_with_sources
    from zataone.policy_engine.hybrid.engine import HybridEngine
    from zataone.policy_engine.hybrid.pack_loader import load_pattern_packs
    from zataone.schemas.document import DocumentSignal

    examples, sources = load_eval_with_sources(str(ONTOLOGY))
    eng = HybridEngine()
    packs = load_pattern_packs()
    existing: set[str] = set()
    for p in packs.values():
        existing.update(t.lower() for t in (p.forbidden_terms or []))
        existing.update(t.lower() for t in (p.forbidden_phrases or []))

    fn_by_cat: dict[str, list[str]] = defaultdict(list)
    comp_by_cat: dict[str, list[str]] = defaultdict(list)
    fn_short = 0

    for ex in examples:
        label = ex.get("label")
        content = (ex.get("content") or "").strip()
        if not content or label not in ("non_compliant", "compliant"):
            continue
        cats = list(ex.get("category_ids") or []) or ["uncategorized"]
        doc = DocumentSignal(
            asset_id=None,
            modality="text",
            normalized_text=content,
            spans=[],
            scene_descriptions=[],
            source_signal_ids=[],
            timeline=[],
            metadata={},
        )
        pred = len(eng.evaluate_full([], document=doc).violations) > 0
        if label == "non_compliant" and not pred:
            if len(content) < 80:
                fn_short += 1
            for c in cats:
                fn_by_cat[c].append(content)
        elif label == "compliant":
            for c in cats:
                comp_by_cat[c].append(content)

    rows: list[dict] = []
    for cat in sorted(fn_by_cat):
        fn_texts = fn_by_cat[cat]
        comp_texts = comp_by_cat.get(cat) or []
        # also use global compliant if category has few pairs
        if len(comp_texts) < 20:
            for texts in comp_by_cat.values():
                comp_texts.extend(texts)
            comp_texts = comp_texts[:2000]

        fn_counts: Counter[str] = Counter()
        comp_counts: Counter[str] = Counter()
        for t in fn_texts:
            fn_counts.update(set(ngrams(t)))
        for t in comp_texts:
            comp_counts.update(set(ngrams(t)))

        scored = []
        for gram, c_fn in fn_counts.items():
            if c_fn < args.min_fn:
                continue
            if gram in existing:
                continue
            c_comp = comp_counts.get(gram, 0)
            # Prefer phrases that barely appear on compliant side
            if c_comp > c_fn:
                continue
            score = log_odds(c_fn, c_comp, len(fn_texts), max(1, len(comp_texts)))
            kind = "phrase" if " " in gram else "term"
            # Prefer multi-word for precision
            if kind == "phrase":
                score += 0.35
            if len(gram) < 80 and len(fn_texts) and any(
                gram in (x.lower()) and len(x) < 100 for x in fn_texts[:50]
            ):
                score += 0.25  # short-ad / slogan signal
            scored.append((score, gram, kind, c_fn, c_comp))

        scored.sort(reverse=True)
        for score, gram, kind, c_fn, c_comp in scored[: args.top]:
            examples_hit = [
                t[:120] for t in fn_texts if gram in t.lower()
            ][:3]
            rows.append(
                {
                    "category_id": cat,
                    "candidate": gram,
                    "kind": kind,
                    "fn_docs": c_fn,
                    "compliant_docs": c_comp,
                    "score": f"{score:.3f}",
                    "already_in_packs": "no",
                    "example_1": examples_hit[0] if examples_hit else "",
                    "example_2": examples_hit[1] if len(examples_hit) > 1 else "",
                    "human_action": "",  # add_phrase | add_term | skip
                    "notes": "",
                }
            )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "category_id",
        "candidate",
        "kind",
        "fn_docs",
        "compliant_docs",
        "score",
        "already_in_packs",
        "example_1",
        "example_2",
        "human_action",
        "notes",
    ]
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"FN texts={sum(len(v) for v in fn_by_cat.values())}  short_fn<{80}={fn_short}")
    print(f"categories={len(fn_by_cat)}  candidates={len(rows)}")
    print(f"wrote {out}")
    print("Review CSV → add high-score phrases to packs (do not bulk-apply terms).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
