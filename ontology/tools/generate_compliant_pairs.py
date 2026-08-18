#!/usr/bin/env python3
"""Generate compliant counterparts for harvested non-compliant ad copy.

The eval set is now ~2,200 non-compliant rows against 190 compliant ones, and all the
compliant rows are generic ("A daily multivitamin to help support your overall wellness").
Generic negatives cannot diagnose a term-matching engine: they share no vocabulary with
the positives, so clearing them proves nothing.

What does diagnose it is a minimal pair — same product, same offer, same risky wording,
lawful because of scope, qualification or disclosure. "Satisfaction guaranteed or your
money back" and "guaranteed weight loss" both contain "guaranteed"; only one is
deceptive. A pack that forbids the bare token fails that pair, which is exactly the
signal we want, and a pair built by deleting the trigger word would have hidden it.

So the instruction below pushes hard on retaining the trigger vocabulary, and the output
records whether it managed to.

Requires GEMINI_API_KEY (and optionally GEMINI_MODEL).

Usage:
    python3.11 ontology/tools/generate_compliant_pairs.py --limit 30   # sample first
    python3.11 ontology/tools/generate_compliant_pairs.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
EXAMPLES = ONTOLOGY / "examples"
CACHE = ONTOLOGY.parent / ".cache" / "compliant_pairs"

TECHNIQUES = [
    "qualification_added",
    "disclosure_added",
    "scope_narrowed",
    "substantiation_cited",
    "typicality_disclosed",
    "material_connection_disclosed",
    "claim_removed",
]

SYSTEM_PROMPT = """\
You are a US advertising-compliance copywriter. For each deceptive ad claim you are given
— verbatim wording an advertiser actually published, which the FTC, a state AG, or BBB
National Programs found deceptive or unsubstantiated — write the closest lawful version
of that same ad.

These become compliant counter-examples in an evaluation set, paired against the original.
Their whole value is being *near misses*, so follow these rules in order.

1. KEEP THE RISKY WORDING WHENEVER A LAWFUL USE OF IT EXISTS. This matters more than
   anything else below. Most trigger words are perfectly legal in the right frame:
     "guaranteed"       -> "Satisfaction guaranteed or your money back"
     "free"             -> "Free shipping on orders over $50"
     "clinically proven"-> "Clinically proven to reduce plaque in a 12-week study"
     "#1"               -> "#1 selling brand in the category, by 2024 unit sales"
   Make it lawful by adding scope, a qualifier, the basis of comparison, or the missing
   disclosure — NOT by deleting the word. A pair that simply drops the trigger word is
   worthless to us.

2. Keep the same product or service, the same offer, the same marketing register, and
   roughly the same length. It must still read like an ad a company would actually run.

3. Never replace the claim with vague filler. "Our product is great" or "A quality
   supplement for your needs" is a failed answer.

4. Qualifiers may be generic but must be plausible and self-contained: "in a 12-week
   company-sponsored study", "results vary", "for simple returns only", "based on 2024
   unit sales". Never name a real institution, journal, study, or person, and never cite
   a specific real statistic you cannot know.

5. Only when the claim is inherently unlawful however it is phrased — a disease-cure
   claim, a promise of guaranteed investment returns, an earnings promise a direct seller
   cannot support — drop that claim and write lawful copy for the same product. Set
   technique to claim_removed and retained_trigger to false. Use this sparingly; rules 1
   and 2 handle most cases.

Report which technique you used, and set retained_trigger true only if the original's
risky wording survives in your version.
"""

RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "compliant_text": {"type": "STRING"},
            "technique": {"type": "STRING", "enum": TECHNIQUES},
            "retained_trigger": {"type": "BOOLEAN"},
        },
        "required": ["id", "compliant_text", "technique", "retained_trigger"],
    },
}


def gemini_json(prompt: str, model: str, key: str, retries: int = 4) -> list[dict]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,  # some variety, or every pair reads identically
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    payload = json.dumps(body).encode()
    for attempt in range(retries):
        request = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = json.load(response)
            parts = data["candidates"][0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            return json.loads(text) if text.strip() else []
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
        except (json.JSONDecodeError, KeyError, IndexError):
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return []
    return []


def build_prompt(batch: list[dict]) -> str:
    lines = ["Write the closest lawful version of each ad claim.\n"]
    for row in batch:
        lines.append(
            f"id: {row['id']}\n"
            f"deceptive_claim: {row['content']}\n"
            f"category: {', '.join(row['category_ids'])}\n"
        )
    return "\n".join(lines)


def run_batch(batch: list[dict], model: str, key: str) -> dict[str, dict]:
    prompt = build_prompt(batch)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / (hashlib.sha256((model + prompt).encode()).hexdigest()[:24] + ".json")
    if cached.exists():
        out = json.loads(cached.read_text())
    else:
        out = gemini_json(prompt, model, key)
        cached.write_text(json.dumps(out))
    return {r["id"]: r for r in out if isinstance(r, dict) and r.get("id")}


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def existing_content() -> set[str]:
    seen: set[str] = set()
    for name in ("eval_seed.yaml", "eval_seed_clean.yaml", "eval_precedents.yaml",
                 "eval_harvested.yaml"):
        path = EXAMPLES / name
        if not path.exists():
            continue
        for ex in (yaml.safe_load(path.read_text()) or {}).get("examples", []) or []:
            if ex.get("content"):
                seen.add(normalize(ex["content"]))
    return seen


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--source", default=str(EXAMPLES / "eval_harvested.yaml"))
    parser.add_argument("--out", default=str(EXAMPLES / "eval_compliant_pairs.yaml"))
    parser.add_argument(
        "--max-per-precedent",
        type=int,
        default=2,
        help="cap so a few heavily-quoted campaigns don't dominate the compliant side",
    )
    parser.add_argument("--limit", type=int, help="cap total pairs generated")
    parser.add_argument("--batch-size", type=int, default=15)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--split", default="test", choices=["train", "dev", "test"])
    args = parser.parse_args()

    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        print("Set GEMINI_API_KEY (or GOOGLE_API_KEY) first.", file=sys.stderr)
        return 2
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    source_rows = yaml.safe_load(Path(args.source).read_text())["examples"]

    per_precedent: dict[str, int] = defaultdict(int)
    selected: list[dict] = []
    for row in source_rows:
        match = re.search(r"derived_from: (\S+?);", row.get("note", ""))
        prec = match.group(1) if match else "unknown"
        if per_precedent[prec] >= args.max_per_precedent:
            continue
        per_precedent[prec] += 1
        selected.append(row)
        if args.limit and len(selected) >= args.limit:
            break

    batches = [selected[i : i + args.batch_size] for i in range(0, len(selected), args.batch_size)]
    print(
        f"source rows: {len(source_rows)}   selected: {len(selected)} "
        f"(max {args.max_per_precedent}/precedent)   batches: {len(batches)}",
        flush=True,
    )

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda b: run_batch(b, model, key), batches))
    verdicts: dict[str, dict] = {}
    for chunk in results:
        verdicts.update(chunk)

    seen = existing_content()
    examples: list[dict] = []
    techniques: dict[str, int] = {}
    retained = 0
    drops: dict[str, int] = {}

    def drop(reason: str) -> None:
        drops[reason] = drops.get(reason, 0) + 1

    for row in selected:
        verdict = verdicts.get(row["id"])
        if not verdict:
            drop("no model output")
            continue
        text = " ".join((verdict.get("compliant_text") or "").split())
        if len(text.split()) < 4:
            drop("too short to be an ad")
            continue
        key_text = normalize(text)
        if not key_text or key_text in seen:
            drop("duplicate of an existing example")
            continue
        if key_text == normalize(row["content"]):
            drop("identical to the non-compliant original")
            continue
        seen.add(key_text)

        techniques[verdict["technique"]] = techniques.get(verdict["technique"], 0) + 1
        if verdict.get("retained_trigger"):
            retained += 1

        examples.append(
            {
                "id": f"{row['id']}_compliant",
                "content": text,
                "modality": row.get("modality", "text"),
                "label": "compliant",
                "category_ids": list(row["category_ids"]),
                "violated_clause_ids": [],
                "jurisdiction": row.get("jurisdiction", "US"),
                "labeled_by": "model",
                "split": args.split,
                "note": (
                    f"compliant minimal pair of {row['id']}; technique: {verdict['technique']}; "
                    f"retained_trigger: {bool(verdict.get('retained_trigger'))}; synthetic"
                ),
            }
        )

    preamble = (
        "# Synthetic COMPLIANT minimal pairs for the harvested non-compliant rows.\n"
        "#\n"
        "# Each row is the closest lawful version of a real deceptive ad: same product, same\n"
        "# offer, and wherever possible the same risky wording, made lawful by scope,\n"
        "# qualification or disclosure. That overlap is the point — a compliant example that\n"
        "# shares no vocabulary with its positive cannot show where a matcher over-fires.\n"
        "#\n"
        "# These are model-written, not observed ads: labeled_by is model and every note says\n"
        "# synthetic. Loaded with ZATAONE_EVAL_INCLUDE_HARVESTED=1, alongside the rows they\n"
        "# pair with — loading the positives without these restores the imbalance they fix.\n"
        "#\n"
        "# Regenerate: python3.11 ontology/tools/generate_compliant_pairs.py\n"
        f"# Total: {len(examples)} pairs, {retained} keeping the original's trigger wording\n\n"
    )
    Path(args.out).write_text(
        preamble + yaml.safe_dump({"examples": examples}, sort_keys=False, allow_unicode=True, width=1000)
    )

    print(f"\ngenerated: {len(examples)}")
    print(f"kept the trigger wording: {retained} ({retained / max(1, len(examples)):.0%})")
    print("techniques:", "  ".join(f"{k}={v}" for k, v in sorted(techniques.items(), key=lambda kv: -kv[1])))
    if drops:
        print("dropped:", "  ".join(f"{k}={v}" for k, v in sorted(drops.items(), key=lambda kv: -kv[1])))
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
