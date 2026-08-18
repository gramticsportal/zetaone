#!/usr/bin/env python3
"""Score the deterministic matcher on compliant/non-compliant minimal pairs.

Each pair is one real deceptive ad and the closest lawful version of it, differing only in
the legally material element. A working matcher fires on the left and clears the right, so
the pair task isolates the thing aggregate accuracy hides: whether the engine is reading
the claim or just spotting topic words. Chance is 50%, which makes it easy to tell when a
change is real.

The dev/test split exists because the thresholds in the pack tooling are tuned against
these same pairs. Tune on dev, quote test. The split is by hash of the example id, so it is
stable across runs and unaffected by file ordering or new rows being added.

Misses are separated into two causes, which need opposite fixes:

  no trigger   — nothing in the packs matched. Broaden triggers, or accept that the wording
                 has no lexical handle and let an embedding channel take it.
  gate cleared — a trigger matched but a qualifier licensed it. Tighten the qualifier
                 patterns; a high number here means the gate is being fooled.

Usage:
    python3.11 ontology/tools/eval_matcher_pairs.py
    python3.11 ontology/tools/eval_matcher_pairs.py --split test --show-fp 15
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ONTOLOGY.parent / "src"))

from zataone.policy_engine.hybrid.lexical import match_lexical  # noqa: E402
from zataone.policy_engine.hybrid.pack_loader import load_pattern_packs  # noqa: E402


def split_of(example_id: str) -> str:
    digest = hashlib.sha1(example_id.encode()).hexdigest()
    return "dev" if int(digest[:8], 16) % 2 == 0 else "test"


def load_pairs() -> list[tuple[dict, dict]]:
    examples = ONTOLOGY / "examples"
    bad = {
        e["id"]: e
        for e in (yaml.safe_load((examples / "eval_harvested.yaml").read_text()) or {}).get("examples", [])
    }
    good = (yaml.safe_load((examples / "eval_compliant_pairs.yaml").read_text()) or {}).get("examples", [])
    pairs = []
    for g in good:
        source = g["id"].removesuffix("_compliant")
        if source in bad:
            pairs.append((bad[source], g))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--split", default="all", choices=["all", "dev", "test"])
    parser.add_argument("--show-fp", type=int, default=0, help="show N most common false-positive sources")
    args = parser.parse_args()

    packs = list(load_pattern_packs().values())
    pairs = [p for p in load_pairs() if args.split == "all" or split_of(p[0]["id"]) == args.split]
    if not pairs:
        print("no pairs found", file=sys.stderr)
        return 1

    def evaluate(text: str) -> tuple[bool, bool]:
        """Return (a trigger matched at all, a hit survived the gate)."""
        triggered = survived = False
        for pack in packs:
            for hit in match_lexical(text, pack, drop_licensed=False):
                triggered = True
                if not hit.licensed_by:
                    survived = True
        return triggered, survived

    both = only_bad = only_good = neither = 0
    no_trigger = gate_cleared = 0
    fp_sources: Counter[str] = Counter()

    start = time.perf_counter()
    for bad, good in pairs:
        bad_trig, bad_fire = evaluate(bad["content"])
        _, good_fire = evaluate(good["content"])

        if bad_fire and good_fire:
            both += 1
        elif bad_fire:
            only_bad += 1
        elif good_fire:
            only_good += 1
        else:
            neither += 1

        if not bad_fire:
            if bad_trig:
                gate_cleared += 1
            else:
                no_trigger += 1

        if good_fire and args.show_fp:
            for pack in packs:
                for hit in match_lexical(good["content"], pack):
                    fp_sources[f"{pack.canonical_id} [{hit.pattern_note or hit.matched_text}]"] += 1

    elapsed_us = (time.perf_counter() - start) / (2 * len(pairs)) * 1e6
    n = len(pairs)
    tp, fp = both + only_bad, both + only_good
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / n
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    print(f"split={args.split}   pairs={n}\n")
    print(f"  fires on both (cannot separate)   {both:5d}  {both / n:5.1%}")
    print(f"  fires on violation only (correct) {only_bad:5d}  {only_bad / n:5.1%}")
    print(f"  fires on compliant only (wrong)   {only_good:5d}  {only_good / n:5.1%}")
    print(f"  fires on neither                  {neither:5d}  {neither / n:5.1%}")
    print(f"\n  recall {recall:.1%}   precision {precision:.1%}   F1 {f1:.3f}   {elapsed_us:.0f} us/ad")
    print("\nwhy violations were missed:")
    print(f"  no trigger matched                {no_trigger:5d}  {no_trigger / n:5.1%}")
    print(f"  trigger matched, gate cleared it  {gate_cleared:5d}  {gate_cleared / n:5.1%}")

    if args.show_fp and fp_sources:
        print("\ntop false-positive sources on lawful copy:")
        for source, count in fp_sources.most_common(args.show_fp):
            print(f"  {count:5d}  {source}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
