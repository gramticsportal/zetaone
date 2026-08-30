#!/usr/bin/env python3
"""Triage harvested candidates with Gemini: advertiser copy vs. the document's own prose.

The harvester is deliberately high-recall, so ~60% of its rows are the enforcement
document talking *about* an ad (complaint narration, statutory language, deposition
excerpts) rather than the ad itself. Telling those apart is a semantic judgement that
regex rules plateau on, so this stage asks a model instead.

This is triage, not ground truth. The project has already been burned by unverified
data, so every row keeps review_status: pending and carries the model's reasoning for
a human to check. An LLM label is a filter that makes curation fast, nothing more.

Requires GEMINI_API_KEY (and optionally GEMINI_MODEL) in the environment.

Usage:
    python3.11 ontology/tools/classify_harvest_candidates.py --limit 50   # sample first
    python3.11 ontology/tools/classify_harvest_candidates.py              # full pass
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
CACHE = ONTOLOGY.parent / ".cache" / "classify"

LABELS = ["ad_copy", "legal_or_narrative", "consumer_statement", "other"]

SYSTEM_PROMPT = """\
You classify short text snippets extracted from US advertising-enforcement documents
(FTC/CFPB/DOJ/FDA complaints, consent orders and judgments).

Each snippet was captured from inside quotation marks in such a document. Your job is to
decide what the quoted text actually is.

Labels:
- ad_copy: verbatim advertiser marketing language — a headline, tagline, product name or
  listing, on-site or in-app copy, email subject, banner, script line, testimonial the
  advertiser published, or UI text the advertiser wrote to persuade or enrol a consumer.
- legal_or_narrative: the document's own words — statutory or regulatory language, defined
  terms, legal standards, the agency's narration of what happened, procedural text,
  internal company communications, deposition or expert testimony.
- consumer_statement: a consumer's own words, e.g. a complaint or review quoted by the agency.
- other: anything else, including unreadable OCR fragments and document headings.

Also judge supports_violation: whether this specific snippet, on its own, is the kind of
claim the enforcement action treated as unlawful.
- yes: the snippet itself carries the problematic claim.
- no: it is unrelated to the violation, or it is compliant/neutral text such as a
  disclaimer or a notice the order later required.
- unclear: plausibly relevant but not decidable from the snippet and its context.

Judge only what the text is. Do not speculate beyond the snippet and its context.
Return one object per input id.
"""

RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "label": {"type": "STRING", "enum": LABELS},
            "supports_violation": {"type": "STRING", "enum": ["yes", "no", "unclear"]},
            "note": {"type": "STRING"},
        },
        "required": ["id", "label", "supports_violation"],
    },
}


def gemini_json(prompt: str, model: str, key: str, retries: int = 4) -> list[dict]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json",
            "responseSchema": RESPONSE_SCHEMA,
            # 2.5-flash spends output budget on reasoning; this task needs none and the
            # budget is better spent on the rows themselves.
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
    lines = ["Classify each snippet.\n"]
    for row in batch:
        context = (row.get("context") or "")[:600]
        lines.append(
            f"id: {row['candidate_id']}\n"
            f"snippet: {row['content']}\n"
            f"surrounding_document_text: {context}\n"
        )
    return "\n".join(lines)


def classify_batch(batch: list[dict], model: str, key: str) -> dict[str, dict]:
    prompt = build_prompt(batch)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / (hashlib.sha256((model + prompt).encode()).hexdigest()[:24] + ".json")
    if cached.exists():
        verdicts = json.loads(cached.read_text(encoding="utf-8"))
    else:
        verdicts = gemini_json(prompt, model, key)
        cached.write_text(json.dumps(verdicts), encoding="utf-8")
    return {v["id"]: v for v in verdicts if isinstance(v, dict) and "id" in v}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--in", dest="infile", default=str(ONTOLOGY / "examples" / "harvest" / "harvest_candidates.yaml"))
    parser.add_argument("--out", default=str(ONTOLOGY / "examples" / "harvest" / "harvest_curated.yaml"))
    parser.add_argument("--csv", default=str(ONTOLOGY / "examples" / "harvest" / "harvest_curated.csv"))
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, help="only classify the first N candidates")
    args = parser.parse_args()

    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        print("Set GEMINI_API_KEY (or GOOGLE_API_KEY) first.", file=sys.stderr)
        return 2
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    rows = yaml.safe_load(Path(args.infile).read_text(encoding="utf-8"))["candidates"]
    if args.limit:
        rows = rows[: args.limit]
    batches = [rows[i : i + args.batch_size] for i in range(0, len(rows), args.batch_size)]
    print(f"classifying {len(rows)} candidates in {len(batches)} batch(es) via {model}...", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda b: classify_batch(b, model, key), batches))

    verdicts: dict[str, dict] = {}
    for chunk in results:
        verdicts.update(chunk)

    counts: dict[str, int] = {}
    support: dict[str, int] = {}
    for row in rows:
        verdict = verdicts.get(row["candidate_id"], {})
        row["llm_label"] = verdict.get("label", "unclassified")
        row["llm_supports_violation"] = verdict.get("supports_violation", "unclear")
        if verdict.get("note"):
            row["llm_note"] = verdict["note"]
        counts[row["llm_label"]] = counts.get(row["llm_label"], 0) + 1
        if row["llm_label"] == "ad_copy":
            k = row["llm_supports_violation"]
            support[k] = support.get(k, 0) + 1

    ad_copy = [r for r in rows if r["llm_label"] == "ad_copy"]
    ready = [r for r in ad_copy if r["llm_supports_violation"] in ("yes", "unclear")]

    Path(args.out).write_text(
        yaml.safe_dump(
            {"candidates": rows}, sort_keys=False, allow_unicode=True, width=100, default_flow_style=False
        ),
        encoding="utf-8",
    )

    import csv as csv_mod

    with open(args.csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv_mod.writer(fh)
        writer.writerow(
            ["candidate_id", "content", "llm_label", "supports_violation", "precedent_id",
             "canonical_ids", "document_page", "document_url", "keep?"]
        )
        for row in sorted(rows, key=lambda r: (r["llm_label"] != "ad_copy", r["precedent_id"])):
            writer.writerow(
                [row["candidate_id"], row["content"], row["llm_label"],
                 row["llm_supports_violation"], row["precedent_id"],
                 "|".join(row["canonical_ids"]), row["document_page"], row["document_url"], ""]
            )

    print(f"\nclassified={sum(1 for r in rows if r['llm_label'] != 'unclassified')}/{len(rows)}")
    print("labels:", "  ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])))
    print("ad_copy supports_violation:", "  ".join(f"{k}={v}" for k, v in sorted(support.items())))
    print(f"\nad_copy={len(ad_copy)}  of which yes/unclear (worth human review)={len(ready)}")
    print(f"\nwrote {args.out}\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
