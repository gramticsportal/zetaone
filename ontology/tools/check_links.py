#!/usr/bin/env python3
"""Audit source-link health across the ontology corpus and precedents.

Reports three classes of problem:

  1. dead links        - URL returns 404/410, or the host does not resolve
  2. missing evidence  - clause has no evidence.source_url (schema requires one)
  3. stale links       - evidence.retrieved_at older than --stale-days

Several agency and platform hosts (sec.gov, finra.org, transparency.meta.com)
return 400/403 to non-browser clients even for perfectly valid pages, so those
statuses are reported as "blocked" rather than dead.

Usage:
    python ontology/tools/check_links.py                  # offline checks only
    python ontology/tools/check_links.py --network        # also probe every URL
    python ontology/tools/check_links.py --network --json report.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml

ONTOLOGY = Path(__file__).resolve().parent.parent
CORPUS = ONTOLOGY / "corpus"
PRECEDENTS = ONTOLOGY / "precedents"

# Hosts that reject automated clients outright; a 4xx from these is not proof of rot,
# so they are reported as "blocked" (verify by hand) rather than failing the run.
# ads.tiktok.com refuses curl, headless fetches and a real browser alike, serving an
# empty body, so its articles cannot be verified from CI at all.
BOT_BLOCKING_HOSTS = {
    "www.sec.gov",
    "www.finra.org",
    "files.brokercheck.finra.org",
    "transparency.meta.com",
    "www.facebook.com",
    "www.instagram.com",
    "support.reddithelp.com",
    "business.reddithelp.com",
    "www5.austlii.edu.au",
    "ads.tiktok.com",
}

# A bare User-Agent is not enough: several .gov hosts (notably consumerfinance.gov)
# reject requests that omit the Accept headers a real browser always sends.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "close",
}

DEAD_STATUSES = {404, 410}


@dataclass
class Finding:
    kind: str
    detail: str
    location: str
    url: str = ""


@dataclass
class Report:
    urls: dict[str, set[str]] = field(default_factory=dict)  # url -> {locations}
    findings: list[Finding] = field(default_factory=list)

    def note_url(self, url: str, location: str) -> None:
        self.urls.setdefault(url, set()).add(location)


def _host(url: str) -> str:
    return re.sub(r"^https?://", "", url).split("/")[0]


def _load(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - surfaced to the operator
        raise SystemExit(f"{path.name}: YAML parse error: {exc}") from exc


def scan_corpus(report: Report, stale_days: int) -> None:
    today = date.today()
    for path in sorted(CORPUS.glob("*.yaml")):
        doc = _load(path)
        for source in doc.get("sources") or []:
            if url := source.get("url"):
                report.note_url(url, f"{path.name}:sources[{source.get('id')}]")
        for clause in doc.get("clauses") or []:
            cid = clause.get("id", "<unknown>")
            where = f"{path.name}:{cid}"
            evidence = clause.get("evidence") or {}
            url = evidence.get("source_url")
            if not url:
                report.findings.append(
                    Finding("missing_evidence", "clause has no evidence.source_url", where)
                )
                continue
            report.note_url(url, where)
            if stale_days and (retrieved := evidence.get("retrieved_at")):
                age = (today - _as_date(retrieved)).days
                if age > stale_days:
                    report.findings.append(
                        Finding("stale", f"retrieved_at is {age} days old", where, url)
                    )


def scan_precedents(report: Report) -> None:
    for path in sorted(PRECEDENTS.glob("*.yaml")):
        doc = _load(path)
        for prec in doc.get("precedents") or []:
            pid = prec.get("precedent_id", "<unknown>")
            where = f"{path.name}:{pid}"
            if url := prec.get("source_url"):
                report.note_url(url, where)
            else:
                report.findings.append(
                    Finding("missing_evidence", "precedent has no source_url", where)
                )
            for i, ev in enumerate(prec.get("evidence") or []):
                if url := ev.get("source_url"):
                    report.note_url(url, f"{where}:evidence[{i}]")


def _as_date(value) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def probe(url: str, timeout: int) -> tuple[int | None, str]:
    """Return (status_code, note). status_code is None when the request failed."""
    request = urllib.request.Request(url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, ""
    except urllib.error.HTTPError as exc:
        return exc.code, ""
    except Exception as exc:  # DNS failure, TLS error, timeout, redirect loop
        return None, type(exc).__name__


def check_network(report: Report, workers: int, timeout: int) -> dict[str, tuple[int | None, str]]:
    urls = sorted(report.urls)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(zip(urls, pool.map(lambda u: probe(u, timeout), urls)))

    for url, (status, note) in results.items():
        locations = sorted(report.urls[url])
        if status in DEAD_STATUSES:
            report.findings.append(
                Finding("dead", f"HTTP {status}", "; ".join(locations), url)
            )
        elif status is None:
            report.findings.append(
                Finding("unreachable", note or "request failed", "; ".join(locations), url)
            )
        elif status >= 400:
            kind = "blocked" if _host(url) in BOT_BLOCKING_HOSTS else "suspect"
            report.findings.append(
                Finding(kind, f"HTTP {status}", "; ".join(locations), url)
            )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--network", action="store_true", help="probe every URL over HTTP")
    parser.add_argument("--stale-days", type=int, default=0, help="flag evidence retrieved_at older than N days (0 = off)")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--json", metavar="PATH", help="write the full report to a JSON file")
    args = parser.parse_args()

    report = Report()
    scan_corpus(report, args.stale_days)
    scan_precedents(report)

    statuses: dict[str, tuple[int | None, str]] = {}
    if args.network:
        statuses = check_network(report, args.workers, args.timeout)

    print(f"urls={len(report.urls)}  files={len(list(CORPUS.glob('*.yaml'))) + len(list(PRECEDENTS.glob('*.yaml')))}")
    if args.network:
        buckets: dict[str, int] = {}
        for status, _ in statuses.values():
            key = "error" if status is None else str(status)
            buckets[key] = buckets.get(key, 0) + 1
        print("http:", "  ".join(f"{k}={v}" for k, v in sorted(buckets.items())))

    blocking = ("dead", "unreachable", "suspect")
    labels = {
        "dead": "DEAD — page is gone, needs a replacement URL",
        "unreachable": "UNREACHABLE — request failed outright",
        "suspect": "SUSPECT — 4xx from a host that normally allows automation",
        "blocked": "BLOCKED — host refuses automation, verify by hand (not a failure)",
        "missing_evidence": "MISSING EVIDENCE",
        "stale": "STALE",
    }
    for kind in ("dead", "unreachable", "suspect", "missing_evidence", "stale", "blocked"):
        hits = [f for f in report.findings if f.kind == kind]
        if not hits:
            continue
        print(f"\n{labels[kind]}  ({len(hits)})")
        for finding in hits:
            print(f"  {finding.detail}  {finding.url}".rstrip())
            print(f"      at {finding.location}")

    if args.json:
        Path(args.json).write_text(
            json.dumps(
                {
                    "urls": {u: sorted(locs) for u, locs in report.urls.items()},
                    "http": {u: s for u, (s, _) in statuses.items()},
                    "findings": [vars(f) for f in report.findings],
                },
                indent=2,
                default=str,
            )
        )
        print(f"\nwrote {args.json}")

    broken = sum(1 for f in report.findings if f.kind in blocking)
    if broken:
        print(f"\nFAIL — {broken} broken link(s)")
        return 1
    print("\nOK — no broken links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
