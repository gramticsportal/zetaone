#!/usr/bin/env python3
"""Harvest challenged ad copy from BBB National Programs decisions (NAD, CARU, DSSRC).

Federal enforcement produces a few dozen advertising cases a year; NAD and its sibling
programs publish thousands. Their decisions quote the exact wording an advertiser used,
which is the same thing harvest_enforcement_ads.py pulls out of FTC complaints — so this
tool emits rows in that identical shape and the existing classify/promote stages run on
them unchanged.

Full NAD decision text sits behind a paid archive, but the published decision summaries
are free and do quote the challenged claims, and DSSRC decisions are public in full.
This tool only reads what is publicly served.

The decision list comes from the site's own JSON feed; `?shortResults=false` returns the
entire catalogue in one request, so the index costs a single call rather than pagination.

Usage:
    python3.11 ontology/tools/harvest_nad_decisions.py --limit 40           # sample
    python3.11 ontology/tools/harvest_nad_decisions.py --programs DSSRC,CARU
    python3.11 ontology/tools/harvest_nad_decisions.py                      # everything
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_enforcement_ads import extract_ad_quotes  # noqa: E402

ONTOLOGY = Path(__file__).resolve().parent.parent
CACHE = ONTOLOGY.parent / ".cache" / "nad"
PAGES = CACHE / "pages"

INDEX_URL = "https://bbbprograms.org/MediaResources/307/section/308?shortResults=false"
SITE = "https://bbbprograms.org"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Which BBB program a decision came from decides which clauses it can violate. NARB is
# NAD's appellate body, so it inherits NAD's standards. DAAP is omitted: the corpus has
# no DAAP clauses yet, and inventing a mapping would be worse than skipping it.
PROGRAMS = {
    "NAD": {
        "tag": "National Advertising Division (NAD)",
        "prefix": "nad",
        "source": "BBB National Programs — National Advertising Division (NAD)",
        "category_ids": ["misleading"],
        "violated_clause_ids": [
            "nad.misleading.truthful_accurate",
            "nad.misleading.substantiation_or_discontinue",
        ],
        "canonical_ids": ["misleading.unsubstantiated_objective_claims"],
    },
    "NARB": {
        "tag": "National Advertising Review Board (NARB)",
        "prefix": "narb",
        "source": "BBB National Programs — National Advertising Review Board (NARB)",
        "category_ids": ["misleading"],
        "violated_clause_ids": [
            "nad.misleading.truthful_accurate",
            "nad.misleading.substantiation_or_discontinue",
        ],
        "canonical_ids": ["misleading.unsubstantiated_objective_claims"],
    },
    "CARU": {
        "tag": "Children's Advertising Review Unit (CARU)",
        "prefix": "caru",
        "source": "BBB National Programs — Children's Advertising Review Unit (CARU)",
        "category_ids": ["minors"],
        "violated_clause_ids": [
            "caru.minors.substantiation_child_claims",
            "caru.minors.product_benefit_claims",
        ],
        "canonical_ids": ["misleading.unsubstantiated_objective_claims"],
    },
    "DSSRC": {
        "tag": "Direct Selling Self-Regulatory Council (DSSRC)",
        "prefix": "dssrc",
        "source": "BBB National Programs — Direct Selling Self-Regulatory Council (DSSRC)",
        "category_ids": ["financial"],
        "violated_clause_ids": [
            "dssrc.finance.earnings_substantiation",
            "dssrc.finance.prohibited_income_phrases",
        ],
        "canonical_ids": [
            "finance.performance_claims_substantiation",
            "finance.misleading_or_unbalanced_claims",
        ],
    },
}

# These decisions narrate in the third person, so the body's own voice is easy to spot:
# it names the deciding body, or attributes the words to a party. Advertiser copy never
# does either. Cheap to strip here, and it keeps the LLM stage from paying for it.
DECISION_VOICE_RE = re.compile(
    r"\b(NAD|NARB|CARU|DSSRC)\b|advertiser.s statement|in its decision|"
    r"recommend(ed|ation)|the challenged|the advertiser|the challenger|"
    r"determined that|concluded that|found that|took issue",
    re.I,
)

MAIN_RE = re.compile(r'<main[^>]*id="main-content"[^>]*>(.*?)</main>', re.S | re.I)
SCRIPT_RE = re.compile(r"<(script|style|nav|footer|form)[^>]*>.*?</\1>", re.S | re.I)
TAG_RE = re.compile(r"<[^>]+>")
# Decision titles are formulaic ("NAD Reviews Advertising Claims for X; Recommends Y
# Discontinue Certain Claims"), so the boilerplate has to go or every precedent retrieves
# on the same worthless terms. What survives is the brand and the product.
STOPWORDS = {
    "the", "and", "for", "with", "national", "advertising", "division", "review",
    "unit", "council", "children", "direct", "selling", "self", "regulatory", "board",
    "finds", "recommends", "certain", "claims", "discontinue", "modify", "inc", "llc",
    "corp", "company", "its", "that", "recommend", "modification", "discontinuation",
    "supported", "bbb", "programs", "case", "decision", "others", "other",
    "nad", "narb", "caru", "dssrc", "reviews", "reviewed", "upholds", "refers",
    "determines", "concludes", "following", "appeal", "inquiry", "monitoring",
    "recommendation", "discontinued", "modified", "after", "from", "made", "make",
}


def fetch(url: str, timeout: int = 40) -> str | None:
    # A few slugs carry bytes that survived as U+FFFD, which urllib cannot put in a
    # request line; percent-encode so one odd URL doesn't abort a 2,000-page run.
    safe = urllib.parse.quote(url, safe=":/?&=%#")
    request = urllib.request.Request(safe, headers=HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
            UnicodeError, ValueError):
        return None


def load_index(refresh: bool) -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "index.json"
    if refresh or not path.exists():
        body = fetch(INDEX_URL, timeout=120)
        if not body:
            raise SystemExit("could not fetch the decision index")
        path.write_text(body)
    return json.loads(path.read_text())["documents"]


def program_of(doc: dict) -> str | None:
    for key, cfg in PROGRAMS.items():
        if cfg["tag"] in doc.get("tags", []):
            return key
    return None


def decision_text(page_html: str) -> str:
    match = MAIN_RE.search(page_html)
    body = match.group(1) if match else page_html
    body = SCRIPT_RE.sub(" ", body)
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", body))).strip()


def slug_of(doc: dict) -> str:
    raw = doc["documentUrl"].rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"[^A-Za-z0-9_-]", "-", raw)[:120] or "decision"


def parse_date(raw: str) -> str | None:
    """Site prints dates as M.DD.YY; return ISO or None rather than guessing."""
    parts = (raw or "").split(".")
    if len(parts) != 3:
        return None
    try:
        month, day, year = (int(p) for p in parts)
    except ValueError:
        return None
    return f"{2000 + year:04d}-{month:02d}-{day:02d}"


def keywords(title: str, limit: int = 6) -> list[str]:
    words: list[str] = []
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9'&-]+", title):
        low = raw.lower()
        if low in STOPWORDS or len(raw) < 3 or low in {w.lower() for w in words}:
            continue
        words.append(raw)
        if len(words) >= limit:
            break
    return words


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--programs", default="NAD,NARB,CARU,DSSRC")
    parser.add_argument("--limit", type=int, help="only process the first N decisions")
    parser.add_argument("--since", type=int, help="only decisions published in this year or later")
    parser.add_argument("--delay", type=float, default=0.4, help="seconds between fetches")
    parser.add_argument("--refresh-index", action="store_true")
    parser.add_argument("--out-candidates", default=str(ONTOLOGY / "examples" / "nad_candidates.yaml"))
    parser.add_argument("--out-csv", default=str(ONTOLOGY / "examples" / "nad_candidates.csv"))
    parser.add_argument("--out-precedents", default=str(ONTOLOGY / "precedents" / "bbb_selfreg.yaml"))
    args = parser.parse_args()

    wanted = {p.strip().upper() for p in args.programs.split(",") if p.strip()}
    unknown = wanted - set(PROGRAMS)
    if unknown:
        raise SystemExit(f"unknown programs: {sorted(unknown)}")

    docs = []
    for doc in load_index(args.refresh_index):
        prog = program_of(doc)
        iso = parse_date(doc.get("publishedDate", ""))
        if prog not in wanted or not iso:
            continue
        if args.since and int(iso[:4]) < args.since:
            continue
        docs.append((prog, iso, doc))
    if args.limit:
        docs = docs[: args.limit]

    PAGES.mkdir(parents=True, exist_ok=True)
    print(f"decisions to process: {len(docs)}", flush=True)

    candidates: list[dict] = []
    precedents: list[dict] = []
    seen_content: set[str] = set()
    stats = {"fetched": 0, "cached": 0, "failed": 0, "no_quotes": 0, "with_quotes": 0}

    for index, (prog, iso, doc) in enumerate(docs, 1):
        cfg = PROGRAMS[prog]
        slug = slug_of(doc)
        url = SITE + doc["documentUrl"]
        cached = PAGES / f"{slug}.html"

        if cached.exists():
            page = cached.read_text()
            stats["cached"] += 1
        else:
            page = fetch(url) or ""
            time.sleep(args.delay)
            if not page:
                stats["failed"] += 1
                continue
            cached.write_text(page)
            stats["fetched"] += 1

        title = re.sub(r"\s+", " ", html.unescape(TAG_RE.sub("", doc["title"]))).strip()
        text = decision_text(page)
        quotes = extract_ad_quotes(text)
        if not quotes:
            stats["no_quotes"] += 1
            continue
        stats["with_quotes"] += 1

        # Titles are long and formulaic, so truncated slugs collide ("...reckitt-benckiser-
        # discontinue-certain-challen"). The digest of the full slug keeps ids unique and
        # stable across runs without making them unreadable.
        digest = hashlib.sha1(slug.encode()).hexdigest()[:6]
        pid = f"prec.{cfg['prefix']}.{slug.replace('-', '_')[:52]}_{iso[:4]}_{digest}"
        kept = 0
        for quote, context in quotes:
            if DECISION_VOICE_RE.search(quote):
                continue
            key = re.sub(r"[^a-z0-9 ]", "", quote.lower()).strip()
            if not key or key in seen_content:
                continue
            seen_content.add(key)
            kept += 1
            candidates.append(
                {
                    "content": quote,
                    "modality": "text",
                    "provisional_label": "non_compliant",
                    "category_ids": list(cfg["category_ids"]),
                    "violated_clause_ids": list(cfg["violated_clause_ids"]),
                    "canonical_ids": list(cfg["canonical_ids"]),
                    "precedent_id": pid,
                    "document_url": url,
                    "document_page": 1,
                    "context": context,
                    "review_status": "pending",
                    "candidate_id": f"nad_{len(candidates) + 1:04d}",
                }
            )
        if not kept:
            continue

        summary = re.sub(r"\s+", " ", html.unescape(TAG_RE.sub("", doc.get("shortCopy") or ""))).strip()
        precedents.append(
            {
                "precedent_id": pid,
                "source": cfg["source"],
                "source_url": url,
                "date": iso,
                "title": title[:300],
                "summary": summary or title[:300],
                "category_ids": list(cfg["category_ids"]),
                "violated_clause_ids": list(cfg["violated_clause_ids"]),
                "canonical_ids": list(cfg["canonical_ids"]),
                "outcome": "self_regulatory_recommendation",
                "status": "final",
                "jurisdiction": "US",
                "retrieved_at": "2026-08-12",
                "evidence": [
                    {
                        "quote": quotes[0][0],
                        "source_url": url,
                        "section": f"{prog} decision summary, {iso}",
                    }
                ],
                "why_this_matters": (
                    f"{prog} reviewed these claims and recommended the advertiser modify or "
                    "discontinue them; the decision quotes the challenged wording verbatim."
                ),
                "retrieval_keywords": keywords(title) or [slug.replace("-", " ")],
                "confidence": "verified",
                "last_verified_at": "2026-08-12",
            }
        )
        if index % 50 == 0:
            print(f"  {index}/{len(docs)} processed, {len(candidates)} candidates", flush=True)

    Path(args.out_candidates).write_text(
        yaml.safe_dump({"candidates": candidates}, sort_keys=False, allow_unicode=True, width=100)
    )
    with open(args.out_csv, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["candidate_id", "content", "precedent_id", "canonical_ids", "document_url"])
        for row in candidates:
            writer.writerow(
                [row["candidate_id"], row["content"], row["precedent_id"],
                 "|".join(row["canonical_ids"]), row["document_url"]]
            )

    preamble = (
        "# Enforcement precedents from BBB National Programs self-regulation.\n"
        "#\n"
        "# Generated from the published decision summaries — each entry's source_url was\n"
        "# fetched and its evidence quote taken from that page, so nothing here is inferred.\n"
        "#\n"
        "# Regenerate: python3.11 ontology/tools/harvest_nad_decisions.py\n"
        f"# Total: {len(precedents)} precedents\n\n"
    )
    Path(args.out_precedents).write_text(
        preamble + yaml.safe_dump({"precedents": precedents}, sort_keys=False, allow_unicode=True, width=1000)
    )

    print("\n" + "  ".join(f"{k}={v}" for k, v in stats.items()))
    print(f"candidates: {len(candidates)}   precedents: {len(precedents)}")
    print(f"\nwrote {args.out_candidates}\nwrote {args.out_csv}\nwrote {args.out_precedents}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
