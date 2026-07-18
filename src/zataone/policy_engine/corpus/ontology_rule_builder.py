# zataone — synthesize engine rules from ontology rules + eval corpus

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any

_STOPWORDS = frozenset(
    """
    a an the and or but if in on at to for of is are was were be been being
    that this with from your must have will they their only also such when where
    does not ads ad can may all any our you we it its as by into about than
    other more most some each per use using used make made over under between
    through during before after above below out off up down
    advertising advertisers advertiser allowed prohibited including without
    required products services content information people users local based
    status options certification target targeting audiences audience
    """.split()
)

_SEVERITY_MAP = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH", "critical": "CRITICAL"}

# Category fallbacks mined from eval_seed non_compliant themes.
_CATEGORY_SEED_TERMS: dict[str, list[str]] = {
    "misleading": [
        "guaranteed", "miracle", "100%", "overnight", "proven", "instant",
        "risk-free", "free money", "act now", "limited time",
    ],
    "health": [
        "cure", "treat", "heal", "eliminate", "fda approved", "clinically proven",
        "weight loss", "before and after", "miracle",
    ],
    "financial": [
        "guaranteed returns", "risk-free", "pre-approved", "passive income",
        "get rich", "no risk", "double your money",
    ],
    "gambling": ["casino", "bet now", "risk-free bet", "welcome bonus", "wager"],
    "drugs": ["cigarette", "vape", "tobacco", "nicotine", "e-cigarette", "cigar"],
    "alcohol": ["beer", "wine", "spirits", "cocktail", "drunk", "hangover free"],
    "political": ["vote for", "paid for by", "elect", "campaign", "ballot"],
    "minors": ["kids", "children", "under 13", "teen", "youth"],
    "privacy": ["sell your data", "opt out", "personal information", "tracking"],
    "discrimination": ["whites only", "no children", "christians only", "adults only"],
    "ip_trademark": ["replica", "counterfeit", "fake designer", "knockoff"],
}


def _tokenize(text: str, *, min_len: int = 4, max_terms: int = 25) -> list[str]:
    if not text:
        return []
    raw = re.findall(r"[a-z][a-z0-9%'-]{2,}", text.lower())
    seen: set[str] = set()
    out: list[str] = []
    for w in raw:
        if w in _STOPWORDS or w in seen:
            continue
        if len(w) < min_len and "%" not in w:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= max_terms:
            break
    return out


def _load_eval_examples(ontology_root: Path) -> list[dict[str, Any]]:
    path = ontology_root / "examples" / "eval_seed.yaml"
    if not path.is_file():
        return []
    import yaml

    data = yaml.safe_load(path.open(encoding="utf-8")) or {}
    return list(data.get("examples") or [])


def _terms_from_eval(
    clause_ids: list[str],
    examples: list[dict[str, Any]],
    *,
    max_terms: int = 15,
) -> list[str]:
    want = set(clause_ids)
    bag: list[str] = []
    for ex in examples:
        if ex.get("label") != "non_compliant":
            continue
        hit = set(ex.get("violated_clause_ids") or []) & want
        if not hit:
            continue
        bag.extend(_tokenize(str(ex.get("content") or ""), max_terms=12))
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in bag:
        if t not in seen:
            seen.add(t)
            out.append(t)
        if len(out) >= max_terms:
            break
    return out


def ontology_rule_to_engine_rule(
    rule: dict[str, Any],
    *,
    clause_texts: list[str],
    eval_examples: list[dict[str, Any]],
    vision_labels: list[str] | None = None,
) -> dict[str, Any]:
    """Convert one ontology rule dict into PolicyEngine-compatible rule."""
    rid = str(rule.get("id") or "")
    category = str(rule.get("category_id") or "")
    clause_ids = [str(c) for c in (rule.get("clause_ids") or [])]
    severity = _SEVERITY_MAP.get(str(rule.get("severity") or "high").lower(), "HIGH")

    terms: list[str] = []
    terms.extend(_terms_from_eval(clause_ids, eval_examples))
    terms.extend(_tokenize(str(rule.get("detection") or "")))
    for text in clause_texts:
        terms.extend(_tokenize(text, max_terms=10))
    terms.extend(_CATEGORY_SEED_TERMS.get(category, [])[:8])

    seen: set[str] = set()
    prohibited: list[str] = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            prohibited.append(t)
        if len(prohibited) >= 20:
            break

    engine: dict[str, Any] = {
        "name": rid.replace("_", " ").title()[:80],
        "description": str(rule.get("detection") or "").strip()[:500],
        "severity": severity,
        "type": "keyword",
        "clause_ids": clause_ids,
        "canonical_id": rule.get("canonical_id"),
        "category_id": category,
        "ontology_rule_id": rid,
    }
    if prohibited:
        engine["prohibited_terms"] = prohibited
    if vision_labels:
        engine["vision_primary_labels"] = vision_labels
    return engine
