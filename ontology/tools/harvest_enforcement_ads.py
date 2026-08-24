#!/usr/bin/env python3
"""Harvest verbatim advertiser copy from the enforcement documents behind each precedent.

Why: pattern packs and the eval seed are built from regulator/platform *policy* prose,
while the matcher scores advertiser *marketing* prose. Complaints and consent orders
quote the offending ad copy verbatim, so they are the one source that yields real
advertiser language already tied to a clause we have mapped.

Pipeline (all hops stay inside links the corpus already contains):

    precedent.source_url ──▶ press release / case page ──▶ complaint & order PDFs
                                                              │
                                                              ▼
                                              verbatim quoted ad copy + provenance

Output is a *candidate* file for human curation. Nothing here is eval-ready: a
complaint also quotes disclaimers, order language and defined terms, so every row
carries review_status: pending and must be confirmed before it enters eval_*.yaml.

Usage:
    python3.11 ontology/tools/harvest_enforcement_ads.py --limit 5      # smoke test
    python3.11 ontology/tools/harvest_enforcement_ads.py                # full run
    python3.11 ontology/tools/harvest_enforcement_ads.py --offline      # cache only
"""

from __future__ import annotations

import argparse
import hashlib
import html
import io
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
PRECEDENTS = ONTOLOGY / "precedents"
CACHE = ONTOLOGY.parent / ".cache" / "enforcement"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "close",
}

# Hosts that refuse automation entirely; skip rather than retry (see check_links.py).
UNREACHABLE_HOSTS = {"ads.tiktok.com", "www.sec.gov", "www.finra.org", "files.brokercheck.finra.org"}

# Only follow one extra hop, and only into pages that list case documents.
CASE_PAGE_HINTS = ("legal-library/browse/cases-proceedings", "/enforcement/actions/", "/legal/murs/")

MAX_PDF_BYTES = 25 * 1024 * 1024
MAX_PDFS_PER_PRECEDENT = 6

# Agency pages promote unrelated cases in sidebars and "latest news" blocks, so a PDF is
# only followed when its link text or filename names a case document.
DOC_TYPE_RE = re.compile(
    r"complaint|consent|stipulat|judgment|order|decision|opinion|petition|settlement|"
    r"cmpt|warning letter|civil penalt",
    re.I,
)

# Tokens too generic to prove a document belongs to a given precedent.
GENERIC_TOKENS = {
    "ftc", "sec", "doj", "cfpb", "fda", "fec", "finra", "hud", "eeoc", "ttb", "commission",
    "federal", "trade", "united", "states", "inc", "llc", "corp", "company", "deceptive",
    "advertising", "misleading", "claims", "marketing", "health", "ads", "consumers",
    "settlement", "charges", "practices", "false", "unfair", "online", "social", "media",
    "dark", "patterns", "privacy", "data", "financial", "credit", "loan", "student",
    "warning", "letter", "covid", "the", "and", "for", "with",
}


# --------------------------------------------------------------------------- quoting

# Complaints quote ad copy with curly quotes far more often than straight ones.
QUOTE_RE = re.compile(r"[\u201c\u201d\"]([^\u201c\u201d\"]{12,300}?)[\u201c\u201d\"]")

# Cue words that mark a passage as describing advertising rather than legal procedure.
# Deliberately excludes "claim" and "represent": both are ubiquitous in legal prose and
# admit far too much boilerplate.
AD_CUES = (
    "advertis", "ad copy", "market", "promot", "website", "web site", "webpage", "banner",
    "commercial", "headline", "landing page", "social media", "packaging", "label",
    "testimonial", "endorse", "campaign", "billboard", "infomercial", "screenshot",
    # Complaints attach the offending creative as a numbered exhibit and describe it by
    # channel, so the channel word is often the only nearby cue.
    "exhibit", "blog", "email", "newsletter", "subject line", "brochure", "flyer",
    "tweet", "video", "press release", "mailer", "circular",
)

# Legal/procedural boilerplate that shows up inside quotes but is never ad copy.
LEGAL_NOISE = re.compile(
    r"u\.s\.c|c\.f\.r|et al|case no|civil action|exhibit|plaintiff|defendant|"
    r"paragraph|hereinafter|pursuant to|jurisdiction|injunctive relief|"
    r"prayer for relief|jury trial|attachment [a-z]\b|section \d|"
    r"ecf no|fed\. ?r\.|f\. ?supp|s\.d\.n\.y|mem\. in|penalty of perjury|"
    r"^means\b|\bmeans any\b|\bmeans a natural person\b|is defined as|"
    r"is likely to mislead|acts or practices|countervailing benefits|"
    r"\b[GCRJ]X\d|\bF\. \d+|the commenter|the commission adopts|proposed rule|"
    r"first amendment|\bat approximately the\b|trade association|"
    r"deposition|expert report|\bwitness\b|\bQ[:.]\s|\bA[:.]\s|\btestified\b|"
    r"express informed consent|material connection|outbound telephone call",
    re.I,
)

# Square brackets mark a court's alteration of a quotation ("confus[ion]", "[W]hat"),
# and section signs mark statutory citations. Genuine ad copy contains neither.
LEGAL_ALTERATION_RE = re.compile(r"[\[\]§]")

# Lettered or numbered list markers from a document's own structure ("D. A press
# release for...").
LIST_MARKER_RE = re.compile(r"^[A-Za-z]\.\s|^\(?[ivxIVX]+\)\s")

# Omnibus publications mention a defendant in passing but contain no ad copy for it.
OMNIBUS_DOC_RE = re.compile(r"semi-annual|semiannual|annual-report|annual_report|transparency-report", re.I)

# A quote that begins mid-sentence yet runs across a sentence boundary is spliced
# narrative, not a claim.
SENTENCE_BOUNDARY_RE = re.compile(r"[.!?]\s+[A-Z]")

# A quote opening with one of these is a fragment of legal argument, not ad copy.
# Kept deliberately narrow: real claims often do start lowercase ("eco-friendly &
# sustainable"), so only function and legal words are excluded.
FRAGMENT_STARTS = {
    "should", "shall", "having", "was", "were", "is", "are", "be", "been", "that",
    "which", "who", "whom", "whose", "and", "or", "but", "by", "within", "without",
    "with", "a", "an", "the", "to", "for", "in", "of", "on", "at", "from", "it",
    "this", "these", "those", "such", "any", "all", "if", "as", "when", "while",
    "because", "whether", "trying", "meant", "under", "upon", "pursuant", "including",
    "provided", "means", "unless", "however", "therefore", "thus", "also", "further",
    "moreover", "additionally", "established", "would", "could", "may", "might",
}

# Precedents that document policy rather than an enforcement action carry no ad copy.
NON_ENFORCEMENT_OUTCOMES = {"guidance"}

# Fragments that indicate we captured a defined term or a citation, not a claim.
DEFINED_TERM_RE = re.compile(r"^(the\s+)?[A-Z][A-Za-z]*(\s+[A-Z][A-Za-z]*){0,2}$")


def looks_like_ad_copy(text: str, context: str) -> bool:
    words = text.split()
    if not 3 <= len(words) <= 45:
        return False
    if LEGAL_NOISE.search(text):
        return False
    if DEFINED_TERM_RE.match(text.strip()):
        return False
    # Reject mid-sentence fragments: PDF text extraction often splits on parentheses.
    if not text[:1].isalnum() or not (text[-1].isalnum() or text[-1] in ".!?%"):
        return False
    if text.count("(") != text.count(")"):
        return False
    if text[:1].isdigit():  # footnote marker swept into the quote
        return False
    if words[0].lower().strip(",.;:") in FRAGMENT_STARTS:
        return False
    if LEGAL_ALTERATION_RE.search(text) or LIST_MARKER_RE.match(text):
        return False
    # A long quote with no terminal punctuation was cut off by the 300-char window.
    if len(text) > 240 and text[-1] not in ".!?":
        return False
    if text[:1].islower() and SENTENCE_BOUNDARY_RE.search(text):
        return False
    letters = sum(c.isalpha() for c in text)
    if letters < 0.6 * len(text):  # page furniture, tables, docket numbers
        return False
    if sum(1 for w in words if len(w) == 1 and w.isalpha()) > 2:  # OCR debris
        return False
    # Require the advertising cue close by; at wider windows legal prose always matches.
    window = context[max(0, len(context) // 2 - 150) : len(context) // 2 + 150].lower()
    if not any(cue in window for cue in AD_CUES):
        return False
    return True


def extract_ad_quotes(page_text: str) -> list[tuple[str, str]]:
    """Return (quote, surrounding_context) pairs that look like advertiser copy."""
    found: dict[str, str] = {}
    for match in QUOTE_RE.finditer(page_text):
        quote = re.sub(r"\s+", " ", html.unescape(match.group(1))).strip(" ,.;:")
        start, end = max(0, match.start() - 320), min(len(page_text), match.end() + 320)
        context = re.sub(r"\s+", " ", page_text[start:end]).strip()
        if looks_like_ad_copy(quote, context) and quote not in found:
            found[quote] = context
    return list(found.items())


# --------------------------------------------------------------------------- fetching

@dataclass
class Fetcher:
    offline: bool = False
    timeout: int = 40
    stats: dict[str, int] = field(default_factory=dict)

    def _bump(self, key: str) -> None:
        self.stats[key] = self.stats.get(key, 0) + 1

    def get(self, url: str) -> bytes | None:
        host = re.sub(r"^https?://", "", url).split("/")[0]
        if host in UNREACHABLE_HOSTS:
            self._bump("skipped_blocked_host")
            return None

        CACHE.mkdir(parents=True, exist_ok=True)
        cached = CACHE / hashlib.sha256(url.encode()).hexdigest()[:24]
        if cached.exists():
            self._bump("cache_hit")
            return cached.read_bytes()
        if self.offline:
            self._bump("cache_miss_offline")
            return None

        try:
            request = urllib.request.Request(url, headers=BROWSER_HEADERS)
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read(MAX_PDF_BYTES)
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as exc:
            self._bump(f"fetch_error_{getattr(exc, 'code', 'net')}")
            return None
        cached.write_bytes(body)
        self._bump("fetched")
        return body


def pdf_links(page_html: str, base_url: str) -> list[str]:
    """PDF links whose anchor text or filename names a case document."""
    links = set()
    for href, anchor in re.findall(r'href="([^"]+)"[^>]*>(.{0,200}?)</a>', page_html, re.S):
        absolute = urllib.parse.urljoin(base_url, html.unescape(href))
        if not absolute.lower().split("?")[0].endswith(".pdf"):
            continue
        label = re.sub(r"<[^>]*>", " ", anchor)
        if DOC_TYPE_RE.search(label) or DOC_TYPE_RE.search(absolute):
            links.add(absolute)
    return sorted(links)


def relevance_tokens(prec: dict) -> set[str]:
    """Distinctive tokens that a document about this precedent should mention."""
    text = " ".join(
        [str(prec.get("title") or ""), " ".join(prec.get("retrieval_keywords") or [])]
    )
    tokens = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z'&-]{3,}", text):
        token = raw.lower()
        if token not in GENERIC_TOKENS:
            tokens.add(token)
    return tokens


def mentions_case(page_texts: list[str], tokens: set[str]) -> bool:
    if not tokens:
        return True  # nothing distinctive to test against; let curation decide
    blob = " ".join(page_texts[:12]).lower()
    return any(token in blob for token in tokens)


def case_page_links(page_html: str, base_url: str) -> list[str]:
    links = set()
    for href in re.findall(r'href="([^"]+)"', page_html):
        absolute = urllib.parse.urljoin(base_url, html.unescape(href))
        if any(hint in absolute for hint in CASE_PAGE_HINTS):
            links.add(absolute.split("?")[0])
    return sorted(links)


def pdf_pages(blob: bytes) -> list[str]:
    import logging

    from pypdf import PdfReader

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        reader = PdfReader(io.BytesIO(blob))
        return [(page.extract_text() or "") for page in reader.pages]
    except Exception:
        return []


# --------------------------------------------------------------------------- harvest

def load_precedents() -> list[dict]:
    out = []
    for path in sorted(PRECEDENTS.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for prec in doc.get("precedents") or []:
            prec["_file"] = path.name
            out.append(prec)
    return out


def documents_for(prec: dict, fetcher: Fetcher) -> list[str]:
    """Resolve the enforcement PDFs reachable from one precedent, at most two hops."""
    seeds = [prec.get("source_url")] + [e.get("source_url") for e in prec.get("evidence") or []]
    seeds = [u for u in dict.fromkeys(filter(None, seeds))]

    pdfs, pages_to_scan = [], []
    for url in seeds:
        (pdfs if url.lower().split("?")[0].endswith(".pdf") else pages_to_scan).append(url)

    for page_url in pages_to_scan:
        body = fetcher.get(page_url)
        if not body:
            continue
        page_html = body.decode("utf-8", "replace")
        pdfs.extend(pdf_links(page_html, page_url))
        # One more hop: press release -> case page -> document list.
        for case_url in case_page_links(page_html, page_url)[:3]:
            case_body = fetcher.get(case_url)
            if case_body:
                pdfs.extend(pdf_links(case_body.decode("utf-8", "replace"), case_url))

    return list(dict.fromkeys(pdfs))[:MAX_PDFS_PER_PRECEDENT]


def harvest_one(prec: dict, fetcher: Fetcher) -> list[dict]:
    rows = []
    tokens = relevance_tokens(prec)
    for doc_url in documents_for(prec, fetcher):
        if OMNIBUS_DOC_RE.search(doc_url):
            fetcher._bump("skipped_omnibus_doc")
            continue
        blob = fetcher.get(doc_url)
        if not blob or not blob[:5].startswith(b"%PDF"):
            continue
        pages = pdf_pages(blob)
        if not mentions_case(pages, tokens):
            fetcher._bump("skipped_offtopic_doc")
            continue
        for page_no, page_text in enumerate(pages, start=1):
            for quote, context in extract_ad_quotes(page_text):
                rows.append(
                    {
                        "content": quote,
                        "modality": "text",
                        "provisional_label": "non_compliant",
                        "category_ids": list(prec.get("category_ids") or []),
                        "violated_clause_ids": list(prec.get("violated_clause_ids") or []),
                        "canonical_ids": list(prec.get("canonical_ids") or []),
                        "precedent_id": prec.get("precedent_id"),
                        "document_url": doc_url,
                        "document_page": page_no,
                        "context": context,
                        "review_status": "pending",
                    }
                )
    return rows


def dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for row in rows:
        key = row["content"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="only process the first N precedents")
    parser.add_argument("--precedent", action="append", help="restrict to specific precedent id(s)")
    parser.add_argument("--offline", action="store_true", help="use cached documents only")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out", default=str(ONTOLOGY / "examples" / "harvest" / "harvest_candidates.yaml"))
    parser.add_argument("--csv", default=str(ONTOLOGY / "examples" / "harvest" / "harvest_candidates.csv"))
    args = parser.parse_args()

    precedents = load_precedents()
    if args.precedent:
        wanted = set(args.precedent)
        precedents = [p for p in precedents if p.get("precedent_id") in wanted]
    else:
        total = len(precedents)
        precedents = [p for p in precedents if p.get("outcome") not in NON_ENFORCEMENT_OUTCOMES]
        print(f"skipped {total - len(precedents)} policy/guidance precedent(s) with no enforcement document")
    if args.limit:
        precedents = precedents[: args.limit]

    fetcher = Fetcher(offline=args.offline)
    print(f"harvesting from {len(precedents)} precedent(s)...", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda p: harvest_one(p, fetcher), precedents))

    rows = dedupe([row for batch in results for row in batch])
    for i, row in enumerate(rows, start=1):
        row["candidate_id"] = f"harv_{i:04d}"

    by_prec: dict[str, int] = {}
    for row in rows:
        by_prec[row["precedent_id"]] = by_prec.get(row["precedent_id"], 0) + 1

    Path(args.out).write_text(
        yaml.safe_dump(
            {"candidates": rows},
            sort_keys=False,
            allow_unicode=True,
            width=100,
            default_flow_style=False,
        ),
        encoding="utf-8",
    )

    import csv as csv_mod

    with open(args.csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv_mod.writer(fh)
        writer.writerow(["candidate_id", "content", "precedent_id", "canonical_ids", "document_page", "document_url", "keep?"])
        for row in rows:
            writer.writerow(
                [row["candidate_id"], row["content"], row["precedent_id"],
                 "|".join(row["canonical_ids"]), row["document_page"], row["document_url"], ""]
            )

    print(f"\ncandidates={len(rows)}  precedents_with_yield={len(by_prec)}/{len(precedents)}")
    print("fetch:", "  ".join(f"{k}={v}" for k, v in sorted(fetcher.stats.items())) or "(none)")
    print("\ntop precedents by yield:")
    for pid, count in sorted(by_prec.items(), key=lambda kv: -kv[1])[:12]:
        print(f"  {count:4d}  {pid}")
    print(f"\nwrote {args.out}\nwrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
