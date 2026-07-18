#!/usr/bin/env python3
"""Phase A: mine hierarchical hybrid pattern packs from the full US ontology corpus.

Reads:
  ontology/corpus/*_us.yaml
  ontology/examples/eval_seed.yaml (+ eval_precedents if present)
  ontology/tools/vision_queries_mined.yaml (optional)

Writes:
  ontology/patterns/_inventory.yaml
  ontology/patterns/by_category/<category_id>.yaml
  ontology/patterns/candidates_review.csv

Run from repo root:
  python ontology/tools/mine_pattern_candidates.py
"""
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"
PATTERNS = ROOT / "patterns"
BY_CAT = PATTERNS / "by_category"

_STOP = frozenset(
    """
    a an the and or but if in on at to for of is are was were be been being
    that this with from your must have will they their only also such when where
    does not ads ad can may all any our you we it its as by into about than
    other more most some each per use using used make made over under between
    through during before after above below out off up down including without
    required products services content information people users local based
    advertising advertisers advertiser allowed prohibited status options
    certification target targeting audiences audience claims claim claim
    """.split()
)

# High-signal seed terms / phrases by category (curated starters).
_CATEGORY_SEEDS: dict[str, dict[str, list[str]]] = {
    "misleading": {
        "terms": [
            "guaranteed", "miracle", "100%", "overnight", "instant", "proven",
            "risk-free", "free money", "act now", "limited time", "immediate",
        ],
        "phrases": [
            "scientifically proven", "doctor recommended", "clinically proven",
            "results may vary",
        ],
        "context": [],
    },
    "health": {
        "terms": [
            "cure", "treat", "heal", "eliminate", "miracle", "disease",
            "cancer", "diabetes", "arthritis",
        ],
        "phrases": [
            "fda approved", "clinically proven", "weight loss", "before and after",
            "cures cancer", "eliminates disease",
        ],
        "context": [
            "pain", "chronic", "inflammation", "symptom", "disease", "condition",
            "arthritis", "diabetes", "asthma", "eczema", "acne", "psoriasis",
            "blood pressure", "cholesterol", "heart", "cancer", "tumor",
        ],
    },
    "financial": {
        "terms": [
            "pre-approved", "passive", "guaranteed", "risk-free", "apr", "loan",
            "crypto", "forex", "investment",
        ],
        "phrases": [
            "guaranteed returns", "get rich", "double your money", "no risk",
            "passive income", "risk free investment",
        ],
        "context": [
            "invest", "investment", "returns", "loan", "credit", "crypto",
            "bitcoin", "forex", "trading", "apr", "interest",
        ],
    },
    "gambling": {
        "terms": ["casino", "wager", "betting", "slots", "poker", "blackjack"],
        "phrases": [
            "bet now", "risk-free bet", "welcome bonus", "real money",
            "online casino", "sports betting",
        ],
        "context": ["casino", "bet", "wager", "gambling", "slots", "poker"],
    },
    "drugs": {
        "terms": [
            "cigarette", "vape", "tobacco", "nicotine", "cigar", "cannabis",
            "marijuana", "weed", "thc", "cbd",
        ],
        "phrases": ["e-cigarette", "smoke free", "nicotine free"],
        "context": ["tobacco", "nicotine", "vape", "cannabis", "marijuana"],
    },
    "alcohol": {
        "terms": ["beer", "wine", "spirits", "cocktail", "liquor", "drunk"],
        "phrases": ["hangover free", "drink now", "happy hour"],
        "context": ["alcohol", "beer", "wine", "liquor", "cocktail"],
    },
    "political": {
        "terms": ["elect", "ballot", "candidate", "campaign", "vote", "pac"],
        "phrases": [
            "vote for", "paid for by", "authorized by", "political advertisement",
        ],
        "context": [
            "vote", "election", "candidate", "campaign", "ballot", "pac",
            "paid for by",
        ],
    },
    "minors": {
        "terms": ["kids", "children", "teen", "youth", "toddler", "infant"],
        "phrases": ["under 13", "under 18", "for children", "kids only"],
        "context": ["child", "children", "kids", "teen", "youth", "minor"],
    },
    "privacy": {
        "terms": ["tracking", "cookies", "pii", "surveillance"],
        "phrases": [
            "sell your data", "opt out", "personal information", "data collection",
        ],
        "context": ["privacy", "data", "tracking", "personal information"],
    },
    "discrimination": {
        "terms": ["whites", "blacks", "muslims", "christians", "immigrants"],
        "phrases": [
            "whites only", "no children", "christians only", "adults only",
            "no immigrants",
        ],
        "context": ["housing", "employment", "credit", "rent", "hire", "loan"],
    },
    "ip_trademark": {
        "terms": ["replica", "counterfeit", "knockoff", "fake", "pirated"],
        "phrases": ["fake designer", "replica handbags", "counterfeit goods"],
        "context": ["brand", "logo", "trademark", "designer", "replica"],
    },
}

# Category-level regex templates (applied when detection/canonical suggests them).
_CATEGORY_REGEX: dict[str, list[dict[str, Any]]] = {
    "misleading": [
        {"pattern": r"\d+%\s+(guaranteed|safe|effective|cure|results?)", "confidence": 0.9,
         "note": "percentage guarantee / efficacy claim"},
        {"pattern": r"(lose|shed)\s+\d+\s+(pounds?|lbs?|kg|kilos?)\s+in\s+\d+\s+(days?|weeks?)",
         "confidence": 0.95, "note": "weight-loss timeframe"},
        {"pattern": r"(in|within)\s+\d+\s+(hours?|days?|weeks?)\s+(guaranteed|or\s+money\s+back)",
         "confidence": 0.85, "note": "time-bound guarantee"},
        {"pattern": r"\b(100\s*%|one\s*hundred\s*percent)\b", "confidence": 0.8,
         "note": "absolute certainty claim"},
    ],
    "health": [
        {"pattern": r"\b(cure[sd]?|heal[sd]?|eliminat(?:e|es|ing))\b.{0,40}\b(cancer|diabetes|arthritis|disease|illness)\b",
         "confidence": 0.9, "note": "cure/heal disease claim"},
        {"pattern": r"\bfda[\s-]*approved\b", "confidence": 0.85, "note": "FDA approved claim"},
        {"pattern": r"\bbefore[\s-]+and[\s-]+after\b", "confidence": 0.8, "note": "before/after imagery cue"},
        {"pattern": r"\bclinically\s+proven\b", "confidence": 0.8, "note": "clinical proof claim"},
    ],
    "financial": [
        {"pattern": r"\bguaranteed\s+(returns?|profits?|income)\b", "confidence": 0.9,
         "note": "guaranteed returns"},
        {"pattern": r"\b(double|triple)\s+your\s+(money|investment)\b", "confidence": 0.9,
         "note": "unrealistic return claim"},
        {"pattern": r"\brisk[\s-]*free\s+(invest|return|profit)", "confidence": 0.85,
         "note": "risk-free investment"},
        {"pattern": r"\b\d+%\s+(apr|return|roi)\b", "confidence": 0.75, "note": "numeric return claim"},
    ],
    "gambling": [
        {"pattern": r"\b(risk[\s-]*free|free)\s+(bet|wager|spin)\b", "confidence": 0.9,
         "note": "risk-free bet offer"},
        {"pattern": r"\b(welcome|deposit)\s+bonus\b", "confidence": 0.8, "note": "gambling bonus"},
        {"pattern": r"\breal[\s-]*money\s+(casino|poker|betting)\b", "confidence": 0.9,
         "note": "real-money gambling"},
    ],
    "political": [
        {"pattern": r"\bpaid\s+for\s+by\b", "confidence": 0.95, "note": "paid-for-by disclaimer cue"},
        {"pattern": r"\b(vote|elect)\s+for\s+\w+", "confidence": 0.85, "note": "vote/elect for"},
        {"pattern": r"\bauthorized\s+by\b", "confidence": 0.8, "note": "authorization disclaimer"},
    ],
    "drugs": [
        {"pattern": r"\b(e[\s-]?cig(?:arette)?s?|vape(?:s|ing)?)\b", "confidence": 0.85,
         "note": "vape / e-cig"},
        {"pattern": r"\b(buy|order|smoke)\s+(weed|cannabis|marijuana|thc)\b", "confidence": 0.9,
         "note": "cannabis purchase cue"},
    ],
    "alcohol": [
        {"pattern": r"\b(buy|order|drink)\s+(beer|wine|vodka|whiskey|liquor)\b", "confidence": 0.8,
         "note": "alcohol CTA"},
    ],
    "minors": [
        {"pattern": r"\bunder\s*(?:the\s*)?(age\s*of\s*)?(13|16|18)\b", "confidence": 0.85,
         "note": "age gate"},
        {"pattern": r"\b(for|aimed\s+at)\s+(kids|children|teens?)\b", "confidence": 0.85,
         "note": "child-directed"},
    ],
    "discrimination": [
        {"pattern": r"\b(no|only)\s+(children|kids|blacks?|whites?|muslims?|christians?|immigrants?)\b",
         "confidence": 0.9, "note": "exclusionary targeting"},
    ],
    "privacy": [
        {"pattern": r"\bsell(?:s|ing)?\s+(your\s+)?(data|personal\s+information)\b", "confidence": 0.85,
         "note": "data sale"},
    ],
    "ip_trademark": [
        {"pattern": r"\b(replica|counterfeit|knock[\s-]?off|fake)\s+\w+", "confidence": 0.85,
         "note": "counterfeit goods"},
    ],
}

# Canonical-id specific extras (high precision).
_CANONICAL_EXTRAS: dict[str, dict[str, Any]] = {
    "misleading.exaggerated_results": {
        "phrases": ["guaranteed results", "miracle cure", "works overnight"],
    },
    "misleading.guaranteed_outcomes": {
        "phrases": ["results in days", "guaranteed overnight", "or your money back"],
        "patterns": [
            {"pattern": r"\b\d+\s*(day|week|hour)s?\s+(results?|guarantee)\b", "confidence": 0.85,
             "note": "timed outcome promise"},
        ],
    },
    "misleading.before_after_distortion": {
        "phrases": ["before and after", "before & after"],
        "vision_labels": ["before after"],
    },
    "health.disease_cure_treatment_claims": {
        "phrases": ["cures cancer", "eliminates diabetes", "heals arthritis"],
    },
    "political.disclaimer_and_authorization": {
        "phrases": ["paid for by", "authorized by", "not authorized by"],
        "vision_min_confidence": 0.6,
    },
    "gambling.real_money_restricted": {
        "phrases": ["real money casino", "sportsbook", "place a bet"],
    },
}


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _tokenize(text: str, *, min_len: int = 4, max_terms: int = 30) -> list[str]:
    if not text:
        return []
    raw = re.findall(r"[a-z][a-z0-9%'-]{2,}", text.lower())
    seen: set[str] = set()
    out: list[str] = []
    for w in raw:
        if w in _STOP or w in seen:
            continue
        if len(w) < min_len and "%" not in w:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= max_terms:
            break
    return out


def _phrases_from_exceptions(raw: Any) -> list[str]:
    if not raw:
        return []
    out: list[str] = []
    for item in raw if isinstance(raw, list) else [raw]:
        s = str(item).strip()
        if not s:
            continue
        # Keep short actionable exception cues; drop long prose.
        if len(s) > 120:
            # pull quoted fragments
            quotes = re.findall(r"'([^']{3,80})'|\"([^\"]{3,80})\"", s)
            for a, b in quotes:
                out.append((a or b).strip().lower())
            continue
        out.append(s.lower())
    return _dedupe(out)


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


def _load_eval_examples() -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for name in ("eval_seed.yaml", "eval_precedents.yaml"):
        path = ROOT / "examples" / name
        if not path.is_file():
            continue
        data = _load_yaml(path)
        examples.extend(data.get("examples") or [])
    return examples


def _load_vision_by_category() -> dict[str, list[str]]:
    path = ROOT / "tools" / "vision_queries_mined.yaml"
    if not path.is_file():
        return {}
    data = _load_yaml(path)
    return dict(data.get("category_vision_queries") or {})


def _eval_terms_for_clauses(
    clause_ids: set[str],
    examples: list[dict[str, Any]],
    *,
    max_terms: int = 20,
) -> tuple[list[str], int]:
    bag: list[str] = []
    hits = 0
    for ex in examples:
        if ex.get("label") != "non_compliant":
            continue
        violated = set(ex.get("violated_clause_ids") or [])
        if not (violated & clause_ids):
            continue
        hits += 1
        bag.extend(_tokenize(str(ex.get("content") or ""), max_terms=15))
    return _dedupe(bag, limit=max_terms), hits


def collect_source_rules() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(CORPUS.glob("*_us.yaml")):
        doc = _load_yaml(path)
        clause_text = {
            str(c.get("id")): str(c.get("text") or "").strip()
            for c in (doc.get("clauses") or [])
            if c.get("id")
        }
        for rule in doc.get("rules") or []:
            if str(rule.get("status", "active")).lower() != "active":
                continue
            rid = str(rule.get("id") or "")
            if not rid:
                continue
            cids = [str(c) for c in (rule.get("clause_ids") or [])]
            rows.append(
                {
                    "source_file": path.name,
                    "rule_id": rid,
                    "canonical_id": str(rule.get("canonical_id") or ""),
                    "category_id": str(rule.get("category_id") or ""),
                    "severity": str(rule.get("severity") or "high").lower(),
                    "modalities": [str(m) for m in (rule.get("modalities") or [])],
                    "detection": str(rule.get("detection") or "").strip(),
                    "exceptions": list(rule.get("exceptions") or []),
                    "clause_ids": cids,
                    "clause_texts": [clause_text.get(c, "") for c in cids if clause_text.get(c)],
                    "priority": int(rule.get("priority") or 50),
                }
            )
    return rows


def build_canonical_packs(
    source_rules: list[dict[str, Any]],
    examples: list[dict[str, Any]],
    vision_by_cat: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    by_can: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in source_rules:
        cid = r["canonical_id"] or f"unmapped.{r['rule_id']}"
        by_can[cid].append(r)

    packs: dict[str, dict[str, Any]] = {}
    for canonical_id, rules in sorted(by_can.items()):
        category = Counter(r["category_id"] for r in rules).most_common(1)[0][0]
        severity = Counter(r["severity"] for r in rules).most_common(1)[0][0]
        clause_ids = _dedupe([c for r in rules for c in r["clause_ids"]])
        modalities = _dedupe([m for r in rules for m in r["modalities"]])
        detections = _dedupe([r["detection"] for r in rules if r["detection"]], limit=8)

        seeds = _CATEGORY_SEEDS.get(category, {})
        terms: list[str] = []
        phrases: list[str] = list(seeds.get("phrases") or [])
        exception_notes: list[str] = []
        exception_terms: list[str] = []

        for r in rules:
            terms.extend(_tokenize(r["detection"], max_terms=12))
            for ct in r["clause_texts"]:
                terms.extend(_tokenize(ct, max_terms=8))
            exception_notes.extend(str(x) for x in r["exceptions"])
            exception_terms.extend(_phrases_from_exceptions(r["exceptions"]))

        eval_terms, eval_hits = _eval_terms_for_clauses(set(clause_ids), examples)
        terms.extend(eval_terms)
        terms.extend(seeds.get("terms") or [])

        extras = _CANONICAL_EXTRAS.get(canonical_id, {})
        phrases.extend(extras.get("phrases") or [])
        terms = _dedupe(terms, limit=40)
        phrases = _dedupe(phrases, limit=25)

        patterns = list(_CATEGORY_REGEX.get(category, []))
        for p in extras.get("patterns") or []:
            patterns.append(p)
        # Dedupe patterns by pattern string
        seen_pat: set[str] = set()
        uniq_patterns: list[dict[str, Any]] = []
        for p in patterns:
            key = p["pattern"]
            if key in seen_pat:
                continue
            seen_pat.add(key)
            uniq_patterns.append(p)

        vision = list(vision_by_cat.get(category, [])[:8])
        vision.extend(extras.get("vision_labels") or [])
        vision = _dedupe(vision, limit=12)

        context_terms = _dedupe(list(seeds.get("context") or []), limit=25)
        # For categories that need context, also pull high-signal tokens from detection.
        if category in ("health", "financial", "discrimination", "political"):
            context_terms = _dedupe(context_terms + terms[:10], limit=30)

        pack = {
            "canonical_id": canonical_id,
            "category_id": category,
            "severity": severity,
            "review_status": "mined",
            "source_rule_ids": [r["rule_id"] for r in rules],
            "source_files": _dedupe([r["source_file"] for r in rules]),
            "clause_ids": clause_ids,
            "modalities": modalities,
            "detection_summaries": detections,
            "forbidden_terms": terms,
            "forbidden_phrases": phrases,
            "forbidden_patterns": uniq_patterns,
            "requires_context": {
                "terms": context_terms,
                "note": "Optional gate: prefer match when context terms appear near hit",
            }
            if context_terms
            else {},
            "exceptions": {
                "terms": _dedupe(exception_terms, limit=20),
                "phrases": [],
                "patterns": [],
                "notes": exception_notes[:12],
            },
            "vision_labels": vision,
            "vision_min_confidence": float(extras.get("vision_min_confidence") or 0.55),
            "embedding_prototypes": detections[:5],
            "eval_non_compliant_hits": eval_hits,
            "notes": (
                "Phase A auto-mined from US ontology corpus + eval. "
                "Curate before Phase B wiring (review_status → curated/approved)."
            ),
        }
        packs[canonical_id] = pack
    return packs


def write_outputs(packs: dict[str, dict[str, Any]], source_rules: list[dict[str, Any]]) -> None:
    PATTERNS.mkdir(parents=True, exist_ok=True)
    BY_CAT.mkdir(parents=True, exist_ok=True)

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for pack in packs.values():
        by_category[pack["category_id"]].append(pack)

    inventory = {
        "schema_version": "1.0.0",
        "phase": "A",
        "jurisdiction": "US",
        "generated_by": "ontology/tools/mine_pattern_candidates.py",
        "counts": {
            "source_rules": len(source_rules),
            "canonical_packs": len(packs),
            "categories": len(by_category),
            "review_status_mined": sum(1 for p in packs.values() if p["review_status"] == "mined"),
        },
        "categories": {
            cat: {
                "canonical_count": len(items),
                "canonical_ids": [p["canonical_id"] for p in sorted(items, key=lambda x: x["canonical_id"])],
            }
            for cat, items in sorted(by_category.items())
        },
        "canonical_index": [
            {
                "canonical_id": p["canonical_id"],
                "category_id": p["category_id"],
                "source_rule_count": len(p["source_rule_ids"]),
                "clause_count": len(p["clause_ids"]),
                "forbidden_term_count": len(p["forbidden_terms"]),
                "forbidden_pattern_count": len(p["forbidden_patterns"]),
                "eval_non_compliant_hits": p["eval_non_compliant_hits"],
                "review_status": p["review_status"],
            }
            for p in sorted(packs.values(), key=lambda x: (x["category_id"], x["canonical_id"]))
        ],
    }
    (PATTERNS / "_inventory.yaml").write_text(
        yaml.dump(inventory, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )

    for cat, items in sorted(by_category.items()):
        doc = {
            "schema_version": "1.0.0",
            "category_id": cat,
            "jurisdiction": "US",
            "phase": "A",
            "review_status": "mined",
            "pack_count": len(items),
            "packs": sorted(items, key=lambda x: x["canonical_id"]),
        }
        (BY_CAT / f"{cat}.yaml").write_text(
            yaml.dump(doc, sort_keys=False, allow_unicode=True, width=100),
            encoding="utf-8",
        )

    # Flatten review CSV for founder curation
    csv_path = PATTERNS / "candidates_review.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "category_id",
                "canonical_id",
                "review_status",
                "severity",
                "source_rule_count",
                "clause_count",
                "eval_hits",
                "top_terms",
                "top_phrases",
                "pattern_count",
                "exception_notes",
                "detection_summary",
            ],
        )
        w.writeheader()
        for p in sorted(packs.values(), key=lambda x: (x["category_id"], x["canonical_id"])):
            w.writerow(
                {
                    "category_id": p["category_id"],
                    "canonical_id": p["canonical_id"],
                    "review_status": p["review_status"],
                    "severity": p["severity"],
                    "source_rule_count": len(p["source_rule_ids"]),
                    "clause_count": len(p["clause_ids"]),
                    "eval_hits": p["eval_non_compliant_hits"],
                    "top_terms": " | ".join(p["forbidden_terms"][:12]),
                    "top_phrases": " | ".join(p["forbidden_phrases"][:8]),
                    "pattern_count": len(p["forbidden_patterns"]),
                    "exception_notes": " || ".join((p.get("exceptions") or {}).get("notes") or [])[:300],
                    "detection_summary": (p["detection_summaries"][0] if p["detection_summaries"] else "")[:200],
                }
            )


def main() -> int:
    source_rules = collect_source_rules()
    examples = _load_eval_examples()
    vision = _load_vision_by_category()
    packs = build_canonical_packs(source_rules, examples, vision)
    write_outputs(packs, source_rules)
    print(
        f"Phase A complete: {len(source_rules)} source rules → "
        f"{len(packs)} canonical packs across "
        f"{len({p['category_id'] for p in packs.values()})} categories"
    )
    print(f"  inventory: {PATTERNS / '_inventory.yaml'}")
    print(f"  by_category: {BY_CAT}/")
    print(f"  review csv: {PATTERNS / 'candidates_review.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
