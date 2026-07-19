# zataone — pattern-pack vocabulary for engine rules (data from ontology/patterns)

"""
Augment corpus-built engine rules with mined pattern-pack vocabulary.

The packs (ontology/patterns/by_category/*.yaml, Phase A approved) carry
phrases/regex/terms mined from real violating ad copy plus context and
exception gates. We adopt the DATA only — matching still runs through our
DSL (RuleEvaluator), keeping rule-level evidence and clause mapping.

Join: pack.source_rule_ids -> engine rule ids. Packs whose source rules are
absent become standalone rules keyed pack_<canonical_id> so no vocabulary
is lost.

Env flags (benchmarked; defaults = best measured config):
  ZATAONE_PATTERN_PACKS=0        disable augmentation entirely
  ZATAONE_PACK_TERMS=1/0         include single forbidden_terms (weak, sec-
                                 ondary per pack QC) in the match body
  ZATAONE_PACK_CONTEXT_GATE=1/0  apply pack requires_context as a hard gate
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {"low": "LOW", "medium": "MEDIUM", "high": "HIGH", "critical": "CRITICAL"}


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def packs_enabled() -> bool:
    return _env_bool("ZATAONE_PATTERN_PACKS", True)


def _include_terms() -> bool:
    return _env_bool("ZATAONE_PACK_TERMS", False)


def _context_gate() -> bool:
    return _env_bool("ZATAONE_PACK_CONTEXT_GATE", False)


def _replace_terms() -> bool:
    """Replace naive builder-tokenized prohibited_terms with pack vocabulary
    (instead of merging). Pack phrases are mined from violating copy; the
    builder's single-word tokens over-fire in document-centric matching."""
    return _env_bool("ZATAONE_PACK_REPLACE_TERMS", False)


def load_pattern_packs(ontology_root: Path) -> list[dict[str, Any]]:
    """All approved packs from by_category/*.yaml; [] if dir absent."""
    pack_dir = ontology_root / "patterns" / "by_category"
    if not pack_dir.is_dir():
        return []
    packs: list[dict[str, Any]] = []
    for path in sorted(pack_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.open(encoding="utf-8")) or {}
        except Exception:
            logger.exception("pattern packs: failed to load %s", path)
            continue
        for pack in doc.get("packs") or []:
            if str(pack.get("review_status", "")).lower() in ("approved", "curated"):
                packs.append(pack)
    return packs


def _pack_vocab(pack: dict[str, Any]) -> tuple[list[str], list[dict[str, Any]]]:
    """(terms-for-body, pattern dicts) from a pack. Phrases always included;
    single terms only when ZATAONE_PACK_TERMS is on (pack QC: 'terms are
    secondary')."""
    body: list[str] = [str(p).strip() for p in pack.get("forbidden_phrases") or [] if str(p).strip()]
    if _include_terms():
        body += [str(t).strip() for t in pack.get("forbidden_terms") or [] if str(t).strip()]
    patterns = [
        {"pattern": str(p["pattern"]), "confidence": float(p.get("confidence", 0.85))}
        for p in pack.get("forbidden_patterns") or []
        if isinstance(p, dict) and p.get("pattern")
    ]
    return body, patterns


def _merge_list(rule: dict, key: str, extra: list) -> None:
    seen = {str(x).lower() if isinstance(x, str) else str(x) for x in rule.get(key) or []}
    merged = list(rule.get(key) or [])
    for item in extra:
        marker = str(item).lower() if isinstance(item, str) else str(item)
        if marker not in seen:
            seen.add(marker)
            merged.append(item)
    if merged:
        rule[key] = merged


def augment_rules_with_packs(
    rules_engine: dict[str, dict], ontology_root: Path
) -> dict[str, int]:
    """Merge pack vocabulary into engine rules in place. Returns stats."""
    if not packs_enabled():
        return {"packs": 0, "augmented_rules": 0, "standalone_rules": 0}

    packs = load_pattern_packs(ontology_root)
    stats = {"packs": len(packs), "augmented_rules": 0, "standalone_rules": 0}

    for pack in packs:
        body_terms, patterns = _pack_vocab(pack)
        exceptions = pack.get("exceptions") or {}
        exception_terms = [
            str(t).strip()
            for t in (exceptions.get("terms") or []) + (exceptions.get("phrases") or [])
            if str(t).strip()
        ]
        context_terms = (
            [str(t).strip() for t in (pack.get("requires_context") or {}).get("terms") or []]
            if _context_gate()
            else []
        )

        targets = [
            rid for rid in (pack.get("source_rule_ids") or []) if rid in rules_engine
        ]
        if targets:
            for rid in targets:
                rule = rules_engine[rid]
                if _replace_terms():
                    rule["prohibited_terms"] = []
                _merge_list(rule, "prohibited_terms", body_terms)
                _merge_list(rule, "patterns", patterns)
                _merge_list(rule, "exception_terms", exception_terms)
                if context_terms:
                    _merge_list(rule, "context_terms", context_terms)
                stats["augmented_rules"] += 1
        elif body_terms or patterns:
            rid = f"pack_{pack.get('canonical_id', 'unknown')}"
            rules_engine[rid] = {
                "name": str(pack.get("canonical_id", rid)).replace("_", " ").title()[:80],
                "description": "; ".join(pack.get("detection_summaries") or [])[:500],
                "severity": _SEVERITY_MAP.get(str(pack.get("severity", "high")).lower(), "HIGH"),
                "type": "keyword",
                "clause_ids": [str(c) for c in pack.get("clause_ids") or []],
                "category_id": str(pack.get("category_id") or ""),
                "canonical_id": pack.get("canonical_id"),
                "prohibited_terms": body_terms,
                "patterns": patterns,
                "exception_terms": exception_terms,
                **({"context_terms": context_terms} if context_terms else {}),
            }
            stats["standalone_rules"] += 1

    logger.info(
        "pattern packs: %(packs)d packs -> %(augmented_rules)d rule augmentations, "
        "%(standalone_rules)d standalone rules",
        stats,
    )
    return stats
