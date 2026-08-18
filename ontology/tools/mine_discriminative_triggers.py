#!/usr/bin/env python3
"""Score pack triggers by how well they actually separate violations from lawful copy.

The current forbidden_terms were mined from policy prose, so they are the vocabulary of
the *rules* rather than of the violations: health.disease_cure_treatment_claims forbids
"regardless" and "legality" because its source sentence said "regardless of legality".
Measured against the compliant minimal pairs, terms like "support", "product" and "health"
fire on lawful copy hundreds of times, and overall precision lands at 43% — below the 50%
you would get by guessing.

This scores every trigger by log-odds ratio with an informative Dirichlet prior (Monroe,
Colaresi & Quinn 2008), comparing non-compliant examples against compliant ones. The prior
is what makes rare terms behave: a term seen twice cannot earn a high score on the strength
of appearing in one corpus and not the other, which a raw ratio would happily grant it.

The threshold matters and is easy to get wrong. A trigger that fires on both sides of a
pair is not necessarily bad: in a gated matcher the trigger is supposed to be
recall-oriented ("proven" appears in 58 violations and 27 lawful ads) and the qualifier
gate downstream supplies the precision. Purging those would gut recall to fix nothing.
What must go are triggers that fire *more* on lawful copy, which is why the bar is z >= 0
rather than a significance level.

Those negatives split into two kinds, and the report separates them:

  noise      — topic words with no bearing on legality: "support", "product", "consumer",
               "data", "time". Delete.
  qualifier  — text that is legally *required*, listed as if it were a violation. The pack
               for political ads forbids "paid for by", the exact disclaimer FECA mandates;
               misleading.guaranteed_outcomes forbids "results may vary", which appears in
               67 lawful ads and 0 violations. These belong in the qualifier gate with
               their sign flipped, not in a forbidden list.

Triggers with too few occurrences to judge are untested, not disproven, and survive
untouched — most alcohol, drugs and political packs have no eval data at all.

Default is a dry-run report. Pass --apply to rewrite the packs.

Usage:
    python3.11 ontology/tools/mine_discriminative_triggers.py
    python3.11 ontology/tools/mine_discriminative_triggers.py --apply
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
PACKS_DIR = ONTOLOGY / "patterns" / "by_category"
EXAMPLES = ONTOLOGY / "examples"

# Occurrences needed before a verdict is trustworthy. Below this the prior dominates and
# the z-score is near zero anyway, but being explicit keeps the purge auditable.
MIN_OCCURRENCES = 8

# Keep any trigger that is not actively more common in lawful copy; the gate handles the
# rest. Below -QUALIFIER_Z a multi-word trigger is almost always a required disclosure that
# was mistakenly forbidden, so it gets reported for promotion into the gate.
KEEP_Z = 0.0
# A stricter bar for bare single tokens looked obviously right — "body", "time", "weight"
# and "business" survived at z >= 0 and produced 72 false positives between them — but
# sweeping it on the dev split moved F1 the wrong way at every setting above zero (0.463 at
# -0.5, 0.454 at 0.0, 0.435 at 0.5, 0.397 at 1.0). The terms it removes carry more recall
# than the precision they cost, so the extra knob is not worth its complexity and one
# threshold applies to everything.
QUALIFIER_Z = 1.5
MINE_Z = 3.0
MINE_MIN_COUNT = 5

TOKEN_RE = re.compile(r"[a-z0-9$%][a-z0-9$%'’-]*")

# Mining ranks by separation, and with pairs that share vocabulary by construction the top
# of that ranking is function words whose counts differ only by corpus size. They are never
# viable triggers, so they are excluded rather than left for a human to skip past.
STOPWORDS = {
    "the", "and", "your", "you", "our", "is", "are", "a", "an", "to", "of", "in", "on",
    "for", "with", "at", "by", "it", "we", "us", "that", "this", "be", "as", "or", "from",
    "will", "can", "any", "all", "more", "get", "now", "new", "up", "out", "so", "if",
    "has", "have", "was", "were", "not", "no", "do", "does", "just", "only", "than",
    "when", "what", "who", "how", "their", "its", "his", "her", "them", "they", "he",
    "she", "i", "my", "me", "one", "two", "s", "t",
}


def is_minable(term: str) -> bool:
    parts = term.split()
    return not all(p in STOPWORDS for p in parts)


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def ngrams(text: str, n_max: int = 3) -> list[str]:
    toks = tokens(text)
    out: list[str] = []
    for n in range(1, n_max + 1):
        out.extend(" ".join(toks[i : i + n]) for i in range(len(toks) - n + 1))
    return out


def load_examples() -> tuple[list[str], list[str], dict[str, tuple[list[str], list[str]]]]:
    """Return (non_compliant, compliant, per-category {cat: (non_compliant, compliant)})."""
    pos: list[str] = []
    neg: list[str] = []
    by_cat: dict[str, tuple[list[str], list[str]]] = defaultdict(lambda: ([], []))
    for name in ("eval_seed.yaml", "eval_precedents.yaml", "eval_harvested.yaml",
                 "eval_compliant_pairs.yaml"):
        path = EXAMPLES / name
        if not path.exists():
            continue
        for ex in (yaml.safe_load(path.read_text()) or {}).get("examples", []) or []:
            label, content = ex.get("label"), ex.get("content") or ""
            if not content:
                continue
            if label == "non_compliant":
                pos.append(content)
                bucket = 0
            elif label == "compliant":
                neg.append(content)
                bucket = 1
            else:
                continue  # borderline: excluded, it is exactly the ambiguous middle
            for cat in ex.get("category_ids") or []:
                by_cat[cat][bucket].append(content)
    return pos, neg, by_cat


def log_odds(pos: list[str], neg: list[str], n_max: int = 3, alpha0: float = 500.0) -> dict[str, tuple[float, int, int]]:
    """Log-odds ratio with an informative Dirichlet prior -> {term: (z, pos_ct, neg_ct)}."""
    cp: Counter[str] = Counter()
    cn: Counter[str] = Counter()
    for t in pos:
        cp.update(set(ngrams(t, n_max)))  # per-document, so one ranty ad can't dominate
    for t in neg:
        cn.update(set(ngrams(t, n_max)))

    background = cp + cn
    total_bg = sum(background.values()) or 1
    n_p, n_n = sum(cp.values()) or 1, sum(cn.values()) or 1

    out: dict[str, tuple[float, int, int]] = {}
    for term, bg in background.items():
        a_w = alpha0 * bg / total_bg
        yp, yn = cp.get(term, 0), cn.get(term, 0)
        num_p = yp + a_w
        num_n = yn + a_w
        den_p = n_p + alpha0 - num_p
        den_n = n_n + alpha0 - num_n
        if den_p <= 0 or den_n <= 0:
            continue
        delta = math.log(num_p / den_p) - math.log(num_n / den_n)
        var = 1.0 / num_p + 1.0 / num_n
        out[term] = (delta / math.sqrt(var), yp, yn)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--apply", action="store_true", help="rewrite packs (default: report only)")
    parser.add_argument("--keep-z", type=float, default=KEEP_Z)
    parser.add_argument("--mine-z", type=float, default=MINE_Z)
    parser.add_argument("--min-occurrences", type=int, default=MIN_OCCURRENCES)
    args = parser.parse_args()

    pos, neg, by_cat = load_examples()
    print(f"non-compliant: {len(pos)}   compliant: {len(neg)}\n")

    global_scores = log_odds(pos, neg)

    total_kept = total_purged = total_untested = 0
    purge_examples: list[tuple[float, str, str, int, int]] = []
    changes: dict[Path, dict] = {}

    for path in sorted(PACKS_DIR.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text())
        cat_kept = cat_purged = cat_untested = 0
        for pack in doc.get("packs", []) or []:
            for field in ("forbidden_terms", "forbidden_phrases"):
                survivors: list[str] = []
                for trigger in pack.get(field) or []:
                    key = " ".join(tokens(trigger))
                    score = global_scores.get(key)
                    if score is None or (score[1] + score[2]) < args.min_occurrences:
                        survivors.append(trigger)  # untested, not disproven
                        cat_untested += 1
                        continue
                    z, yp, yn = score
                    if z >= args.keep_z:
                        survivors.append(trigger)
                        cat_kept += 1
                    else:
                        cat_purged += 1
                        purge_examples.append((z, pack["canonical_id"], trigger, yp, yn))
                pack[field] = survivors
        total_kept += cat_kept
        total_purged += cat_purged
        total_untested += cat_untested
        changes[path] = doc
        print(f"{path.stem:16s} kept={cat_kept:4d}  purged={cat_purged:4d}  untested={cat_untested:4d}")

    print(f"\nTOTAL            kept={total_kept}  purged={total_purged}  untested={total_untested}")

    promote = sorted(x for x in purge_examples if x[0] <= -QUALIFIER_Z and " " in x[2])
    noise = sorted(x for x in purge_examples if (x[0] > -QUALIFIER_Z or " " not in x[2]))

    if promote:
        print("\nrequired disclosures that were listed as violations — promote to the gate:")
        seen: set[str] = set()
        for z, pack_id, trigger, yp, yn in promote:
            if trigger in seen:
                continue
            seen.add(trigger)
            print(f"  z={z:+6.2f}  non_compliant={yp:4d} compliant={yn:4d}  {trigger[:36]:36s}  {pack_id}")

    print("\ntopic noise removed:")
    for z, pack_id, trigger, yp, yn in noise[:18]:
        print(f"  z={z:+6.2f}  non_compliant={yp:4d} compliant={yn:4d}  {trigger[:36]:36s}  {pack_id}")

    print(f"\ncandidate new triggers per category (z >= {args.mine_z}, count >= {MINE_MIN_COUNT}):")
    for cat, (cpos, cneg) in sorted(by_cat.items()):
        if len(cpos) < 30 or len(cneg) < 30:
            print(f"  {cat:14s} skipped — {len(cpos)} non-compliant / {len(cneg)} compliant is too little to mine")
            continue
        scores = log_odds(cpos, cneg)
        top = [
            (z, t, yp, yn)
            for t, (z, yp, yn) in scores.items()
            if z >= args.mine_z and yp >= MINE_MIN_COUNT and is_minable(t)
        ]
        top.sort(reverse=True)
        print(f"  {cat:14s} ({len(cpos)} pos / {len(cneg)} neg) -> {len(top)} candidates")
        for z, t, yp, yn in top[:12]:
            print(f"      z={z:5.1f}  {yp:4d}/{yn:<4d}  {t}")

    if args.apply:
        for path, doc in changes.items():
            doc["qc_note"] = (
                "Triggers filtered by discriminative log-odds against compliant minimal "
                "pairs (mine_discriminative_triggers.py); policy-prose terms removed."
            )
            path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=1000))
        print(f"\napplied to {len(changes)} pack files")
    else:
        print("\n(dry run — pass --apply to rewrite the packs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
