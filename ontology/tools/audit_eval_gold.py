#!/usr/bin/env python3
"""Build a human-review queue for the eval gold set, with optional Gemini justifications.

Priority = rows where label quality is most doubtful or most costly if wrong:
  high   — matcher FN / FP (disagreement with gold), or very short copy
  medium — harvested / pair rows that are assessable but not yet human-confirmed
  low    — TP / TN on seed+precedents (spot-check only)

Without --gemini: writes a review CSV ranked by priority (matcher tags only).
With --gemini: also asks Gemini whether the gold label is plausible and why,
so you can clear or quarantine rows faster. Gemini is advisory — you decide.

Usage (repo root):
  # Fast: queue only (no API)
  PYTHONPATH=src python3.11 ontology/tools/audit_eval_gold.py --priority high --limit 100

  # With Gemini justifications (needs GEMINI_API_KEY)
  PYTHONPATH=src python3.11 ontology/tools/audit_eval_gold.py --gemini --priority high --limit 50

  # Full harvest quality pass (also see audit_missed_violations.py)
  PYTHONPATH=src python3.11 ontology/tools/audit_eval_gold.py --gemini --priority high,medium

Outputs:
  ontology/examples/harvest/eval_gold_review.csv
  ontology/examples/harvest/eval_gold_review.html   (easier browser review)

Fill human_decision: keep | drop | relabel_nc | relabel_c | quarantine
Then apply drops via quarantine / hand edit (see eval README).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ONTOLOGY = ROOT / "ontology"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ONTOLOGY))

CACHE = ROOT / ".cache" / "eval_gold_audit"
OUT_CSV = ONTOLOGY / "examples" / "harvest" / "eval_gold_review.csv"
OUT_HTML = ONTOLOGY / "examples" / "harvest" / "eval_gold_review.html"

SYSTEM_PROMPT = """\
You are helping a human audit gold labels for a US advertising-compliance eval set.
Each row has: claimed gold_label (non_compliant | compliant), category hints, and ad text.
The text may be harvested from enforcement docs (noisy) or expert-written.

For each row return:
  quality: assessable_claim | fragment | not_a_claim
    assessable_claim — self-contained ad claim a reviewer can rule on alone
    fragment — truncated / context-dependent; not judgeable alone
    not_a_claim — product name only, legal prose, heading, not ad copy

  label_agree: agree | disagree | unsure
    agree — gold_label is the right call for this text as written
    disagree — gold_label is wrong for this text as written
    unsure — need more context (e.g. missing disclosure / image)

  suggested_label: non_compliant | compliant | drop
    drop when quality is fragment or not_a_claim

  reason: one or two short sentences justifying the call (cite the claim wording).
  Do not invent surrounding context that is not in the text.
"""

RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "quality": {
                "type": "STRING",
                "enum": ["assessable_claim", "fragment", "not_a_claim"],
            },
            "label_agree": {"type": "STRING", "enum": ["agree", "disagree", "unsure"]},
            "suggested_label": {
                "type": "STRING",
                "enum": ["non_compliant", "compliant", "drop"],
            },
            "reason": {"type": "STRING"},
        },
        "required": ["id", "quality", "label_agree", "suggested_label", "reason"],
    },
}


def gemini_json(prompt: str, model: str, key: str, retries: int = 4) -> list[dict]:
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={key}"
    )
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
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                data = json.load(resp)
            parts = data["candidates"][0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
            return json.loads(text) if text.strip() else []
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(2**attempt * 2)
                continue
            raise
        except (json.JSONDecodeError, KeyError, IndexError):
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return []
    return []


def run_batch(batch: list[dict], model: str, key: str) -> dict[str, dict]:
    lines = []
    for r in batch:
        cats = ",".join(r.get("category_ids") or []) or "?"
        lines.append(
            f"id: {r['id']}\ngold_label: {r['label']}\ncategories: {cats}\n"
            f"text: {r['content']}\n"
        )
    prompt = "Audit each row.\n\n" + "\n".join(lines)
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / (hashlib.sha256((model + prompt).encode()).hexdigest()[:24] + ".json")
    if cached.exists():
        out = json.loads(cached.read_text(encoding="utf-8"))
    else:
        out = gemini_json(prompt, model, key)
        cached.write_text(json.dumps(out), encoding="utf-8")
    return {r["id"]: r for r in out if isinstance(r, dict) and r.get("id")}


def priority_for(row: dict) -> str:
    err = row["error_type"]
    n = row["content_len"]
    src = row["source"]
    if err in ("FN", "FP") or n < 80:
        return "high"
    if src in ("eval_harvested.yaml", "eval_compliant_pairs.yaml"):
        return "medium"
    if row["label"] == "borderline":
        return "medium"
    return "low"


def write_html(rows: list[dict], path: Path) -> None:
    parts = [
        "<!DOCTYPE html><html><head><meta charset=utf-8><title>Eval gold review</title>",
        "<style>",
        "body{font:14px/1.45 system-ui,sans-serif;margin:24px;max-width:1100px}",
        "h1{font-size:1.3rem}.meta{color:#555;margin-bottom:1.5rem}",
        ".card{border:1px solid #ddd;border-radius:8px;padding:14px 16px;margin:12px 0}",
        ".high{border-left:4px solid #c0392b}.medium{border-left:4px solid #d68910}",
        ".low{border-left:4px solid #7f8c8d}",
        ".tag{display:inline-block;background:#eee;border-radius:4px;padding:1px 7px;",
        "margin-right:6px;font-size:12px}",
        ".fn{background:#fdecea}.fp{background:#fef5e7}.tp{background:#eafaf1}",
        ".disagree{background:#fadbd8}.content{white-space:pre-wrap;background:#fafafa;",
        "padding:10px;border-radius:6px;margin:8px 0}",
        ".reason{color:#1a5276}",
        "</style></head><body>",
        "<h1>Eval gold review queue</h1>",
        f"<p class=meta>{len(rows)} rows — fill <code>human_decision</code> in the CSV</p>",
    ]
    for r in rows:
        err = r.get("error_type") or ""
        agree = r.get("gemini_label_agree") or ""
        parts.append(f"<div class='card {html.escape(r.get('priority') or '')}'>")
        parts.append(
            f"<div><span class='tag'>{html.escape(r.get('priority') or '')}</span>"
            f"<span class='tag {html.escape(err.lower())}'>{html.escape(err)}</span>"
            f"<span class='tag'>{html.escape(r.get('label') or '')}</span>"
            f"<span class='tag'>{html.escape(r.get('source') or '')}</span>"
            f"<code>{html.escape(r.get('id') or '')}</code></div>"
        )
        parts.append(f"<div class=content>{html.escape(r.get('content') or '')}</div>")
        if r.get("gemini_reason"):
            sug = r.get("gemini_suggested_label") or ""
            q = r.get("gemini_quality") or ""
            parts.append(
                f"<p class='reason'><strong>Gemini</strong> "
                f"[{html.escape(agree)} / {html.escape(q)} → {html.escape(sug)}]: "
                f"{html.escape(r['gemini_reason'])}</p>"
            )
        parts.append("</div>")
    parts.append("</body></html>")
    path.write_text("".join(parts), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--priority",
        default="high",
        help="comma list: high,medium,low (default high)",
    )
    parser.add_argument("--limit", type=int, help="cap rows after priority filter")
    parser.add_argument("--gemini", action="store_true", help="call Gemini for justifications")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--out-csv", default=str(OUT_CSV))
    parser.add_argument("--out-html", default=str(OUT_HTML))
    args = parser.parse_args()

    os.environ.setdefault("ZATAONE_HYBRID_ENGINE", "1")
    os.environ.setdefault("ZATAONE_HYBRID_NLP", "0")

    from examples.load_eval import load_eval_with_sources
    from zataone.policy_engine.hybrid.engine import HybridEngine
    from zataone.schemas.document import DocumentSignal

    examples, sources = load_eval_with_sources(str(ONTOLOGY))
    eng = HybridEngine()
    want = {p.strip().lower() for p in args.priority.split(",") if p.strip()}

    scored: list[dict] = []
    for ex in examples:
        label = ex.get("label")
        content = (ex.get("content") or "").strip()
        if not content:
            continue
        doc = DocumentSignal(
            asset_id=None,
            modality=ex.get("modality") or "text",
            normalized_text=content,
            spans=[],
            scene_descriptions=[],
            source_signal_ids=[],
            timeline=[],
            metadata={"eval_id": ex.get("id")},
        )
        n_viol = len(eng.evaluate_full([], document=doc, active_rule_ids=None).violations)
        pred_pos = n_viol > 0
        if label == "non_compliant":
            err = "TP" if pred_pos else "FN"
        elif label == "compliant":
            err = "FP" if pred_pos else "TN"
        else:
            err = "BORDERLINE_HIT" if pred_pos else "BORDERLINE_MISS"

        row = {
            "id": ex.get("id"),
            "source": sources.get(ex["id"], "?"),
            "label": label,
            "category_ids": list(ex.get("category_ids") or []),
            "content": content,
            "content_len": len(content),
            "matcher_viol": n_viol,
            "error_type": err,
        }
        row["priority"] = priority_for(row)
        scored.append(row)

    filtered = [r for r in scored if r["priority"] in want]
    # Review order: FN first, then FP, then short, then rest
    order = {"FN": 0, "FP": 1, "BORDERLINE_HIT": 2, "BORDERLINE_MISS": 3, "TP": 4, "TN": 5}
    filtered.sort(
        key=lambda r: (
            {"high": 0, "medium": 1, "low": 2}.get(r["priority"], 9),
            order.get(r["error_type"], 9),
            r["content_len"],
        )
    )
    if args.limit:
        filtered = filtered[: args.limit]

    print(
        f"scored={len(scored)}  queue={len(filtered)}  "
        f"priorities={sorted(want)}  "
        f"FN={sum(1 for r in scored if r['error_type']=='FN')}  "
        f"FP={sum(1 for r in scored if r['error_type']=='FP')}"
    )

    gemini: dict[str, dict] = {}
    if args.gemini:
        key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
        if not key:
            print("Set GEMINI_API_KEY (or GOOGLE_API_KEY) for --gemini", file=sys.stderr)
            return 2
        model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
        batches = [
            filtered[i : i + args.batch_size]
            for i in range(0, len(filtered), args.batch_size)
        ]
        print(f"gemini batches={len(batches)} model={model}", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            chunks = list(pool.map(lambda b: run_batch(b, model, key), batches))
        for chunk in chunks:
            gemini.update(chunk)

    out_rows: list[dict] = []
    for r in filtered:
        g = gemini.get(r["id"] or "", {})
        out_rows.append(
            {
                "priority": r["priority"],
                "error_type": r["error_type"],
                "id": r["id"],
                "source": r["source"],
                "gold_label": r["label"],
                "category_ids": "|".join(r["category_ids"]),
                "content_len": r["content_len"],
                "matcher_viol": r["matcher_viol"],
                "content": r["content"],
                "gemini_quality": g.get("quality", ""),
                "gemini_label_agree": g.get("label_agree", ""),
                "gemini_suggested_label": g.get("suggested_label", ""),
                "gemini_reason": g.get("reason", ""),
                "human_decision": "",
                "human_notes": "",
            }
        )

    out_csv = Path(args.out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    fields = list(out_rows[0].keys()) if out_rows else [
        "priority",
        "error_type",
        "id",
        "source",
        "gold_label",
        "category_ids",
        "content_len",
        "matcher_viol",
        "content",
        "gemini_quality",
        "gemini_label_agree",
        "gemini_suggested_label",
        "gemini_reason",
        "human_decision",
        "human_notes",
    ]
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(out_rows)

    out_html = Path(args.out_html)
    write_html(
        [
            {
                **r,
                "label": r["gold_label"],
                "gemini_reason": r["gemini_reason"],
                "gemini_label_agree": r["gemini_label_agree"],
                "gemini_quality": r["gemini_quality"],
                "gemini_suggested_label": r["gemini_suggested_label"],
            }
            for r in out_rows
        ],
        out_html,
    )

    if args.gemini:
        disagree = sum(1 for r in out_rows if r["gemini_label_agree"] == "disagree")
        dropish = sum(
            1
            for r in out_rows
            if r["gemini_quality"] in ("fragment", "not_a_claim")
            or r["gemini_suggested_label"] == "drop"
        )
        print(f"gemini disagree={disagree}  drop_candidates={dropish}")

    print(f"wrote {out_csv}")
    print(f"wrote {out_html}")
    print(
        "Next: open the HTML/CSV, fill human_decision "
        "(keep|drop|relabel_nc|relabel_c|quarantine), then apply edits."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
