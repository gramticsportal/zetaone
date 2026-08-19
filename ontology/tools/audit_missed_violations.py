#!/usr/bin/env python3
"""Judge whether harvested violations are actually judgeable claims.

The harvester pulled verbatim spans out of enforcement documents, and some of what it kept
are sentence fragments — "curved and stretchy fit", "has your back every day", "gel without
the light" — which no reviewer could call deceptive in isolation, because the deception
lived in the surrounding paragraph the harvester discarded. A first pass over the rows the
matcher misses found 34% of them in that state.

It audits **every** harvested row, not only the missed ones, and that is the whole point.
Auditing just the misses and deleting the junk found there would remove noise exclusively
from the rows the matcher fails on, leaving whatever junk it happens to catch in place as
true positives. Recall would jump because the eval set had been trimmed to flatter it. The
rows the matcher catches have to face the same judge as the rows it misses.

Splits rows into:

  assessable_claim  a self-contained advertising claim a reviewer could rule on
  fragment          truncated or context-dependent; not judgeable on its own
  not_a_claim       narrative, legal or descriptive text that is not an ad claim at all

The realistic recall ceiling is the assessable share, not 100%. Rows labelled fragment or
not_a_claim are candidates for removal from the eval set, which raises measured recall
without changing a line of matcher code — worth knowing before attributing that gap to the
engine.

Requires GEMINI_API_KEY (or GOOGLE_API_KEY). Writes a CSV so the labels can be spot-checked
by hand; the model is triaging here, not deciding.

Usage:
    python3.11 ontology/tools/audit_missed_violations.py               # every row
    python3.11 ontology/tools/audit_missed_violations.py --limit 200   # sample, for a look
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ONTOLOGY.parent / "src"))

from zataone.policy_engine.hybrid.lexical import match_lexical  # noqa: E402
from zataone.policy_engine.hybrid.pack_loader import load_pattern_packs  # noqa: E402

CACHE = ONTOLOGY.parent / ".cache" / "missed_audit"
LABELS = ["assessable_claim", "fragment", "not_a_claim"]

SYSTEM_PROMPT = """\
You are auditing an evaluation set for US advertising-compliance software. Each row was
extracted automatically from an FTC complaint, a state attorney-general filing, or a BBB
National Programs decision, and is supposed to be a verbatim advertising claim that a
regulator found deceptive. The extraction was noisy, and your job is to say which rows are
usable — not whether the claim is lawful.

Label each row:

  assessable_claim  A self-contained advertising claim. A compliance reviewer could read
                    this alone and say what is being promised and whether it needs
                    substantiation or a disclosure. Example: "Clinically proven to reverse
                    hair loss in 30 days".

  fragment          Real ad wording, but cut off or dependent on text that is missing, so
                    nobody could rule on it as it stands. Examples: "than a mop and
                    bucket", "gel without the light", "curved and stretchy fit".

  not_a_claim       Not advertising copy: narrative from the legal document, a heading, a
                    product name on its own, procedural or descriptive text.

Judge only what is written. Do not imagine the surrounding ad, and do not treat a claim as
assessable because you can guess the product category. If you would have to ask "in what
context?" before ruling on it, it is a fragment.
"""

RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "label": {"type": "STRING", "enum": LABELS},
            "reason": {"type": "STRING"},
        },
        "required": ["id", "label", "reason"],
    },
}


def gemini_json(prompt: str, model: str, key: str, retries: int = 4) -> list[dict]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    payload = json.dumps(body).encode()
    for attempt in range(retries):
        request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
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


def run_batch(batch: list[dict], model: str, key: str) -> dict[str, dict]:
    prompt = "Label each row.\n\n" + "\n".join(f"id: {r['id']}\ntext: {r['content']}\n" for r in batch)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / (hashlib.sha256((model + prompt).encode()).hexdigest()[:24] + ".json")
    if cached.exists():
        out = json.loads(cached.read_text())
    else:
        out = gemini_json(prompt, model, key)
        cached.write_text(json.dumps(out))
    return {r["id"]: r for r in out if isinstance(r, dict) and r.get("id")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="sample this many rows instead of auditing all")
    parser.add_argument("--out", default=str(ONTOLOGY / "examples" / "harvest_quality_audit.csv"))
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=11)
    args = parser.parse_args()

    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        print("Set GEMINI_API_KEY (or GOOGLE_API_KEY) first.", file=sys.stderr)
        return 2
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    packs = list(load_pattern_packs().values())
    rows = yaml.safe_load((ONTOLOGY / "examples" / "eval_harvested.yaml").read_text())["examples"]

    def fires(text: str) -> bool:
        return any(match_lexical(text, p, drop_licensed=False) for p in packs)

    missed = sum(1 for r in rows if not fires(r["content"]))
    print(f"harvested violations: {len(rows)}   matching no trigger: {missed} ({missed / len(rows):.1%})")

    if args.limit:
        random.seed(args.seed)
        sample = random.sample(rows, min(args.limit, len(rows)))
    else:
        sample = rows
    batches = [sample[i : i + args.batch_size] for i in range(0, len(sample), args.batch_size)]
    print(f"auditing {len(sample)} rows in {len(batches)} batches\n", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda b: run_batch(b, model, key), batches))
    verdicts: dict[str, dict] = {}
    for chunk in results:
        verdicts.update(chunk)

    counts: Counter[str] = Counter()
    by_outcome: dict[str, Counter[str]] = {"fires": Counter(), "misses": Counter()}
    with open(args.out, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "label", "matcher", "reason", "content"])
        for row in sample:
            verdict = verdicts.get(row["id"])
            if not verdict:
                counts["<no verdict>"] += 1
                continue
            outcome = "fires" if fires(row["content"]) else "misses"
            counts[verdict["label"]] += 1
            by_outcome[outcome][verdict["label"]] += 1
            writer.writerow(
                [row["id"], verdict["label"], outcome, verdict.get("reason", ""), row["content"]]
            )

    judged = sum(counts[label] for label in LABELS)
    print("composition:")
    for label, count in counts.most_common():
        print(f"  {label:18s} {count:5d}  {count / max(1, len(sample)):5.1%}")

    # If junk were spread evenly, cleaning would not move recall much; if it clusters in the
    # misses, part of the recall gap was never the matcher's fault. Either way the cleaning
    # has to be applied to both groups, which is why the whole set is audited.
    print("\nassessable share, split by whether the matcher fires:")
    for outcome, counter in by_outcome.items():
        total = sum(counter.values())
        if total:
            print(f"  {outcome:7s} {counter['assessable_claim'] / total:5.1%} assessable  (n={total})")

    if judged:
        print(
            f"\n{counts['assessable_claim'] / judged:.0%} of harvested rows are genuinely "
            f"assessable claims; the rest are extraction noise."
        )
    print(f"\nwrote {args.out} — spot-check before acting on it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
