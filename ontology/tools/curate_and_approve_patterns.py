#!/usr/bin/env python3
"""Phase A QC: clean mined pattern packs and mark approved.

Re-reads by_category/*.yaml, applies denoise + precision rules, rewrites packs
with review_status=approved, refreshes _inventory.yaml and candidates_review.csv.

Run:
  python ontology/tools/mine_pattern_candidates.py   # optional refresh
  python ontology/tools/curate_and_approve_patterns.py
"""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = ROOT / "patterns"
BY_CAT = PATTERNS / "by_category"

# Tokens that come from legal/detection prose, not ad copy.
_NOISE = frozenset(
    """
    missing complying laws silence periods destinations comply legal requirements
    verified regions verification contain identifies complete process communications
    internet lacking clear conspicuous stating unverified including without required
    allowed prohibited must shall policy policies advertisers advertising advertisement
    ads ad content users people services products information based local status
    options certification targeting audiences audience claims claim practices practice
    standard standards guidelines guideline section meta google tiktok linkedin amazon
    platform platforms regulator social issues elections politics issue electoral
    authorization disclaimer disclosure disclosures statements statement language
    example examples such like etc via using used make made specific certain various
    related relevant appropriate applicable result results result result
    destinations destination advertisers advertiser promoting promote promotes
    promotion promotions material materials entity entities association associations
    outlet outlets news famous person persons image images imply implying
    endorsement affiliation misuse misrepresenting misrepresent
    """.split()
)

# Ultra-generic terms that fire everywhere if left as forbidden_terms alone.
_TOO_GENERIC = frozenset(
    """
    free money real risk return returns invest investment credit loan loans
    paid vote vote campaign ballot candidate class size error training test
    """.split()
)

# Per-canonical curated high-precision overlays (terms/phrases only; regex from miner kept).
_CURATED: dict[str, dict[str, Any]] = {
    "misleading.exaggerated_results": {
        "terms": ["guaranteed", "miracle", "100%", "overnight", "instant", "proven"],
        "phrases": [
            "scientifically proven", "clinically proven", "doctor recommended",
            "guaranteed results", "miracle cure", "works overnight",
        ],
    },
    "misleading.guaranteed_outcomes": {
        "terms": ["guaranteed", "overnight", "instant", "100%"],
        "phrases": [
            "results may vary", "or your money back", "guaranteed overnight",
            "results in days",
        ],
    },
    "misleading.before_after_distortion": {
        "terms": [],
        "phrases": ["before and after", "before & after", "transformation photos"],
        "vision_labels": ["before after"],
        "vision_min_confidence": 0.55,
    },
    "misleading.false_affiliation_or_endorsement": {
        "terms": [],
        "phrases": ["as seen on", "endorsed by", "official partner", "celebrity endorsed"],
    },
    "health.disease_cure_treatment_claims": {
        "terms": ["cure", "heal", "eliminate"],
        "phrases": [
            "cures cancer", "eliminates diabetes", "heals arthritis",
            "fda approved", "clinically proven",
        ],
        "requires_context": [
            "disease", "cancer", "diabetes", "arthritis", "illness", "symptom",
            "pain", "chronic", "condition",
        ],
    },
    "health.negative_self_perception_body_image": {
        "terms": [],
        "phrases": ["before and after", "lose weight fast", "get thin", "ugly body"],
    },
    "finance.guaranteed_returns_or_risk_free": {
        "terms": ["risk-free"],
        "phrases": [
            "guaranteed returns", "guaranteed profits", "risk free investment",
            "double your money", "no risk", "passive income guaranteed",
        ],
        "requires_context": [
            "invest", "investment", "returns", "profit", "roi", "crypto", "trading",
        ],
    },
    "finance.crypto_restricted": {
        "terms": ["crypto", "bitcoin", "nft", "token"],
        "phrases": ["buy bitcoin", "crypto investment", "guaranteed crypto"],
    },
    "gambling.realmoney_requires_license_and_authorization": {
        "terms": ["casino", "wager", "slots"],
        "phrases": [
            "real money casino", "sports betting", "risk-free bet", "welcome bonus",
            "place a bet",
        ],
    },
    "gambling.social_casino_no_real_money": {
        "terms": [],
        "phrases": ["real money", "cash prizes", "win real cash"],
    },
    "political.authorization_and_disclaimer_required": {
        "terms": [],
        "phrases": ["paid for by", "authorized by", "not authorized by", "vote for"],
        "requires_context": [
            "vote", "elect", "election", "candidate", "campaign", "ballot", "pac",
            "paid for by",
        ],
        "vision_labels": ["campaign poster", "election badge"],
        "vision_min_confidence": 0.65,
        "notes": "Vision-only political hits need OCR/context; min confidence 0.65",
    },
    "political.paid_political_ads_prohibited": {
        "terms": [],
        "phrases": ["political advertisement", "vote for", "elect", "campaign contribution"],
        "requires_context": ["vote", "elect", "election", "candidate", "campaign"],
        "vision_min_confidence": 0.65,
    },
    "political.synthetic_content_disclosure": {
        "terms": [],
        "phrases": ["ai generated", "synthetic media", "deepfake", "digitally altered"],
    },
    "atc.tobacco_and_nicotine_ads_prohibited": {
        "terms": ["cigarette", "vape", "tobacco", "nicotine", "cigar"],
        "phrases": ["e-cigarette", "buy vapes", "smoke cigarettes"],
    },
    "atc.recreational_drugs_and_thc_prohibited": {
        "terms": ["cannabis", "marijuana", "weed", "thc"],
        "phrases": ["buy weed", "order cannabis", "thc gummies"],
    },
    "atc.alcohol_age_and_location_targeting_required": {
        "terms": ["beer", "wine", "liquor", "cocktail"],
        "phrases": ["buy beer", "drink now", "happy hour special"],
        "requires_context": ["alcohol", "beer", "wine", "liquor", "21+", "drink"],
    },
    "discrimination.discriminatory_ad_content_prohibited": {
        "terms": [],
        "phrases": [
            "whites only", "no children", "christians only", "no immigrants",
            "adults only",
        ],
        "requires_context": ["housing", "rent", "employment", "hire", "credit", "loan"],
    },
    "minors.age_restricted_products_not_shown_to_minors": {
        "terms": [],
        "phrases": ["for kids", "under 13", "under 18", "aimed at children"],
    },
    "privacy.sensitive_data_misuse": {
        "terms": [],
        "phrases": ["sell your data", "we track you", "personal information sold"],
    },
    "ip_trademark.counterfeit_goods": {
        "terms": ["replica", "counterfeit", "knockoff"],
        "phrases": ["fake designer", "replica handbags", "counterfeit goods"],
    },
}


def _dedupe(items: list[str], *, limit: int | None = None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        x = str(x).strip().lower()
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
        if limit is not None and len(out) >= limit:
            break
    return out


def _clean_terms(terms: list[str], *, keep_max: int = 18) -> list[str]:
    out: list[str] = []
    for t in terms:
        t = str(t).strip().lower()
        if not t or len(t) < 3 and "%" not in t:
            continue
        if t in _NOISE or t in _TOO_GENERIC:
            continue
        # Drop pure function words / legalese leftovers
        if re.fullmatch(r"[a-z]{1,3}", t) and "%" not in t:
            continue
        out.append(t)
    return _dedupe(out, limit=keep_max)


def _clean_phrases(phrases: list[str], *, keep_max: int = 16) -> list[str]:
    out: list[str] = []
    for p in phrases:
        p = str(p).strip().lower()
        if not p or len(p) < 5:
            continue
        # Drop exception-like soft phrases from forbidden list
        if p.startswith("results may vary") or "permitted under" in p:
            continue
        out.append(p)
    return _dedupe(out, limit=keep_max)


def _validate_patterns(patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in patterns or []:
        pat = p.get("pattern")
        if not pat or pat in seen:
            continue
        try:
            re.compile(pat)
        except re.error:
            continue
        seen.add(pat)
        out.append(
            {
                "pattern": pat,
                "confidence": float(p.get("confidence") or 0.8),
                "note": str(p.get("note") or ""),
            }
        )
    return out


def curate_pack(pack: dict[str, Any]) -> dict[str, Any]:
    cid = pack["canonical_id"]
    curated = dict(_CURATED.get(cid, {}))

    terms = _clean_terms(list(pack.get("forbidden_terms") or []))
    phrases = _clean_phrases(list(pack.get("forbidden_phrases") or []))
    patterns = _validate_patterns(list(pack.get("forbidden_patterns") or []))

    if curated.get("terms") is not None:
        # Prefer curated terms as primary; keep a few cleaned mined terms as supplement
        terms = _dedupe(list(curated["terms"]) + terms, limit=20)
    if curated.get("phrases") is not None:
        phrases = _dedupe(list(curated["phrases"]) + phrases, limit=18)

    ctx = list((pack.get("requires_context") or {}).get("terms") or [])
    if curated.get("requires_context") is not None:
        ctx = list(curated["requires_context"])
    ctx = _dedupe([c for c in ctx if c not in _NOISE], limit=25)

    vision = list(pack.get("vision_labels") or [])
    if curated.get("vision_labels") is not None:
        vision = list(curated["vision_labels"])
    vision = _dedupe(vision, limit=10)
    vision_min = float(
        curated.get("vision_min_confidence")
        or pack.get("vision_min_confidence")
        or 0.55
    )
    if pack.get("category_id") == "political":
        vision_min = max(vision_min, 0.65)

    exceptions = dict(pack.get("exceptions") or {})
    # Move soft exception phrases out of forbidden if present
    exception_terms = _dedupe(
        list(exceptions.get("terms") or [])
        + ["results may vary", "for entertainment", "informational only", "no real money"],
        limit=20,
    )

    # Approval gate: must have at least one of phrases/patterns/terms after clean
    has_signal = bool(terms or phrases or patterns)
    # Prefer requiring phrase or regex for approval (terms alone too noisy)
    strong = bool(phrases or patterns)
    status = "approved" if has_signal and strong else "curated"

    notes = [
        "Phase A QC approved via curate_and_approve_patterns.py.",
        "Prefer phrase/regex hits; terms are secondary.",
        "Political vision_min_confidence elevated to reduce FP (campaign poster).",
    ]
    if curated.get("notes"):
        notes.append(str(curated["notes"]))
    if pack.get("notes"):
        notes.append(str(pack["notes"])[:200])

    out = dict(pack)
    out.update(
        {
            "review_status": status,
            "forbidden_terms": terms,
            "forbidden_phrases": phrases,
            "forbidden_patterns": patterns,
            "requires_context": {
                "terms": ctx,
                "note": "Gate: prefer match when context terms appear near hit",
            }
            if ctx
            else {},
            "exceptions": {
                "terms": exception_terms,
                "phrases": list(exceptions.get("phrases") or []),
                "patterns": list(exceptions.get("patterns") or []),
                "notes": list(exceptions.get("notes") or [])[:12],
            },
            "vision_labels": vision,
            "vision_min_confidence": vision_min,
            "qc": {
                "cleaned": True,
                "has_phrases": bool(phrases),
                "has_patterns": bool(patterns),
                "has_terms": bool(terms),
                "approval_rule": "approved if phrases or patterns present after denoise",
            },
            "notes": " ".join(notes),
        }
    )
    return out


def _smoke_tests(packs_by_cat: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Lightweight phrase/regex smoke checks for QC report."""
    cases = [
        ("positive", "misleading", "guaranteed miracle overnight results 100%"),
        ("positive", "health", "this pill cures cancer and eliminates diabetes"),
        ("positive", "financial", "guaranteed returns risk-free investment double your money"),
        ("positive", "gambling", "real money casino welcome bonus risk-free bet"),
        ("positive", "political", "vote for smith paid for by citizens for change"),
        ("negative", "political", "approximation estimation error underfitting overfitting hypothesis class"),
        ("negative", "misleading", "approximation estimation error underfitting overfitting hypothesis class"),
    ]
    report = []
    for kind, cat, text in cases:
        t = text.lower()
        hits = []
        for pack in packs_by_cat.get(cat, []):
            matched = []
            for ph in pack.get("forbidden_phrases") or []:
                if ph in t:
                    matched.append(f"phrase:{ph}")
            for pat in pack.get("forbidden_patterns") or []:
                if re.search(pat["pattern"], t, flags=re.I):
                    matched.append(f"regex:{pat['note'] or pat['pattern'][:40]}")
            # terms only if phrase/regex empty for this check — count separately
            term_hits = [x for x in (pack.get("forbidden_terms") or []) if x in t]
            if matched:
                hits.append({"canonical_id": pack["canonical_id"], "matches": matched[:6]})
            elif term_hits and kind == "positive":
                hits.append(
                    {
                        "canonical_id": pack["canonical_id"],
                        "matches": [f"term:{x}" for x in term_hits[:4]],
                        "weak": True,
                    }
                )
        report.append(
            {
                "kind": kind,
                "category": cat,
                "text": text,
                "hit_count": len(hits),
                "hits": hits[:6],
                "pass": (len(hits) > 0) if kind == "positive" else (len(hits) == 0),
            }
        )
    return {
        "cases": report,
        "passed": sum(1 for r in report if r["pass"]),
        "total": len(report),
    }


def main() -> int:
    packs_by_cat: dict[str, list[dict[str, Any]]] = {}
    all_packs: list[dict[str, Any]] = []

    for path in sorted(BY_CAT.glob("*.yaml")):
        doc = yaml.safe_load(path.open(encoding="utf-8")) or {}
        cleaned = [curate_pack(p) for p in (doc.get("packs") or [])]
        packs_by_cat[doc.get("category_id") or path.stem] = cleaned
        all_packs.extend(cleaned)
        out_doc = {
            "schema_version": "1.0.0",
            "category_id": doc.get("category_id") or path.stem,
            "jurisdiction": "US",
            "phase": "A",
            "review_status": "approved",
            "pack_count": len(cleaned),
            "qc_note": "Denoised and approved by curate_and_approve_patterns.py",
            "packs": cleaned,
        }
        path.write_text(
            yaml.dump(out_doc, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )

    smoke = _smoke_tests(packs_by_cat)
    approved = sum(1 for p in all_packs if p["review_status"] == "approved")
    curated_only = sum(1 for p in all_packs if p["review_status"] == "curated")

    inventory = {
        "schema_version": "1.0.0",
        "phase": "A",
        "jurisdiction": "US",
        "qc_status": "approved" if smoke["passed"] == smoke["total"] else "approved_with_warnings",
        "generated_by": "ontology/tools/curate_and_approve_patterns.py",
        "counts": {
            "canonical_packs": len(all_packs),
            "categories": len(packs_by_cat),
            "review_status_approved": approved,
            "review_status_curated": curated_only,
            "smoke_passed": smoke["passed"],
            "smoke_total": smoke["total"],
        },
        "smoke_tests": smoke,
        "categories": {
            cat: {
                "canonical_count": len(items),
                "canonical_ids": [p["canonical_id"] for p in items],
                "approved": sum(1 for p in items if p["review_status"] == "approved"),
            }
            for cat, items in sorted(packs_by_cat.items())
        },
        "canonical_index": [
            {
                "canonical_id": p["canonical_id"],
                "category_id": p["category_id"],
                "review_status": p["review_status"],
                "forbidden_term_count": len(p["forbidden_terms"]),
                "forbidden_phrase_count": len(p["forbidden_phrases"]),
                "forbidden_pattern_count": len(p["forbidden_patterns"]),
                "vision_min_confidence": p["vision_min_confidence"],
                "eval_non_compliant_hits": p.get("eval_non_compliant_hits", 0),
            }
            for p in sorted(all_packs, key=lambda x: (x["category_id"], x["canonical_id"]))
        ],
        "approval_notes": [
            "All packs denoised (detection-prose noise removed).",
            "Political vision_min_confidence >= 0.65.",
            "Approved = has phrases or regex after QC; curated = terms-only residual.",
            "Ready for Phase B hybrid evaluator (BM25 shortlist → match packs).",
        ],
    }
    (PATTERNS / "_inventory.yaml").write_text(
        yaml.dump(inventory, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )

    csv_path = PATTERNS / "candidates_review.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "category_id",
                "canonical_id",
                "review_status",
                "severity",
                "term_count",
                "phrase_count",
                "pattern_count",
                "vision_min_confidence",
                "eval_hits",
                "top_phrases",
                "top_terms",
            ],
        )
        w.writeheader()
        for p in sorted(all_packs, key=lambda x: (x["category_id"], x["canonical_id"])):
            w.writerow(
                {
                    "category_id": p["category_id"],
                    "canonical_id": p["canonical_id"],
                    "review_status": p["review_status"],
                    "severity": p.get("severity", ""),
                    "term_count": len(p["forbidden_terms"]),
                    "phrase_count": len(p["forbidden_phrases"]),
                    "pattern_count": len(p["forbidden_patterns"]),
                    "vision_min_confidence": p["vision_min_confidence"],
                    "eval_hits": p.get("eval_non_compliant_hits", 0),
                    "top_phrases": " | ".join(p["forbidden_phrases"][:8]),
                    "top_terms": " | ".join(p["forbidden_terms"][:10]),
                }
            )

    print(f"QC complete: {approved} approved, {curated_only} curated-only (of {len(all_packs)})")
    print(f"Smoke tests: {smoke['passed']}/{smoke['total']} passed")
    for case in smoke["cases"]:
        mark = "PASS" if case["pass"] else "FAIL"
        print(f"  [{mark}] {case['kind']:8} {case['category']:12} hits={case['hit_count']}")
    print(f"Inventory: {PATTERNS / '_inventory.yaml'}")
    return 0 if smoke["passed"] == smoke["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
