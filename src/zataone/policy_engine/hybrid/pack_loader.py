# zataone — load approved Phase A pattern packs

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_SEVERITY_FLOAT = {"low": 0.2, "medium": 0.4, "high": 0.7, "critical": 1.0}


@dataclass
class PatternPack:
    canonical_id: str
    category_id: str
    severity: str
    review_status: str
    source_rule_ids: list[str] = field(default_factory=list)
    clause_ids: list[str] = field(default_factory=list)
    forbidden_terms: list[str] = field(default_factory=list)
    forbidden_phrases: list[str] = field(default_factory=list)
    forbidden_patterns: list[dict[str, Any]] = field(default_factory=list)
    requires_context_terms: list[str] = field(default_factory=list)
    exception_terms: list[str] = field(default_factory=list)
    exception_notes: list[str] = field(default_factory=list)
    vision_labels: list[str] = field(default_factory=list)
    vision_min_confidence: float = 0.55
    embedding_prototypes: list[str] = field(default_factory=list)
    modalities: list[str] = field(default_factory=list)
    detection_summaries: list[str] = field(default_factory=list)
    # Qualifier classes that license this pack's triggers. Empty means absolute: no
    # disclaimer makes the conduct lawful, so a hit is never cleared.
    qualifier_classes: list[str] = field(default_factory=list)

    @property
    def is_absolute(self) -> bool:
        return not self.qualifier_classes

    @property
    def severity_float(self) -> float:
        return _SEVERITY_FLOAT.get(str(self.severity).lower(), 0.7)

    @property
    def primary_rule_id(self) -> str:
        return self.source_rule_ids[0] if self.source_rule_ids else self.canonical_id


def resolve_patterns_root(ontology_root: Path | None = None) -> Path | None:
    if ontology_root is not None:
        p = ontology_root / "patterns" / "by_category"
        return p if p.is_dir() else None
    here = Path(__file__).resolve()
    candidates = [
        here.parents[4] / "ontology" / "patterns" / "by_category",  # src/zataone/...
        here.parents[3] / "ontology" / "patterns" / "by_category",
        Path.cwd() / "ontology" / "patterns" / "by_category",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    # Walk up looking for ontology/
    for parent in here.parents:
        p = parent / "ontology" / "patterns" / "by_category"
        if p.is_dir():
            return p
    return None


@lru_cache(maxsize=8)
def load_qualifiers(patterns_root: Path) -> tuple[dict[str, list[re.Pattern[str]]], dict[str, list[str]]]:
    """Return (class_id -> compiled patterns, pack canonical_id -> required class ids).

    Compiled once and cached: the packs are small enough to score exhaustively on every
    request, so the only thing worth avoiding is recompiling regexes in the hot path.
    """
    path = patterns_root / "qualifiers.yaml"
    if not path.is_file():
        logger.warning("hybrid pack_loader: qualifiers.yaml not found; gate disabled")
        return {}, {}
    doc = yaml.safe_load(path.open(encoding="utf-8")) or {}

    compiled: dict[str, list[re.Pattern[str]]] = {}
    for entry in doc.get("classes") or []:
        cid = str(entry.get("id") or "")
        if not cid:
            continue
        pats: list[re.Pattern[str]] = []
        for raw in entry.get("patterns") or []:
            try:
                pats.append(re.compile(str(raw), re.IGNORECASE))
            except re.error as exc:
                logger.warning("qualifiers.yaml: bad pattern in %s: %s", cid, exc)
        compiled[cid] = pats

    requirements: dict[str, list[str]] = {}
    for pack_id, classes in (doc.get("pack_requirements") or {}).items():
        wanted = [str(c) for c in (classes or [])]
        unknown = [c for c in wanted if c not in compiled]
        if unknown:
            logger.warning("qualifiers.yaml: %s references unknown classes %s", pack_id, unknown)
        requirements[str(pack_id)] = [c for c in wanted if c in compiled]
    return compiled, requirements


def load_pattern_packs(
    *,
    ontology_root: Path | None = None,
    approved_only: bool = True,
) -> dict[str, PatternPack]:
    """Load packs keyed by canonical_id."""
    root = resolve_patterns_root(ontology_root)
    if root is None:
        logger.warning("hybrid pack_loader: patterns/by_category not found")
        return {}
    _, requirements = load_qualifiers(root.parent)

    packs: dict[str, PatternPack] = {}
    for path in sorted(root.glob("*.yaml")):
        doc = yaml.safe_load(path.open(encoding="utf-8")) or {}
        for raw in doc.get("packs") or []:
            status = str(raw.get("review_status") or "mined").lower()
            if approved_only and status not in ("approved", "curated"):
                continue
            cid = str(raw.get("canonical_id") or "")
            if not cid:
                continue
            ctx = raw.get("requires_context") or {}
            exc = raw.get("exceptions") or {}
            packs[cid] = PatternPack(
                canonical_id=cid,
                category_id=str(raw.get("category_id") or ""),
                severity=str(raw.get("severity") or "high"),
                review_status=status,
                source_rule_ids=[str(x) for x in (raw.get("source_rule_ids") or [])],
                clause_ids=[str(x) for x in (raw.get("clause_ids") or [])],
                forbidden_terms=[str(x).lower() for x in (raw.get("forbidden_terms") or [])],
                forbidden_phrases=[str(x).lower() for x in (raw.get("forbidden_phrases") or [])],
                forbidden_patterns=list(raw.get("forbidden_patterns") or []),
                requires_context_terms=[
                    str(x).lower() for x in (ctx.get("terms") or [])
                ],
                exception_terms=[str(x).lower() for x in (exc.get("terms") or [])],
                exception_notes=[str(x) for x in (exc.get("notes") or [])],
                vision_labels=[str(x).lower() for x in (raw.get("vision_labels") or [])],
                vision_min_confidence=float(raw.get("vision_min_confidence") or 0.55),
                embedding_prototypes=[
                    str(x) for x in (raw.get("embedding_prototypes") or [])
                ],
                modalities=[str(x) for x in (raw.get("modalities") or [])],
                detection_summaries=[
                    str(x) for x in (raw.get("detection_summaries") or [])
                ],
                qualifier_classes=requirements.get(cid, []),
            )
    logger.info("hybrid pack_loader: loaded %d packs from %s", len(packs), root)
    return packs


def build_rule_to_canonical(packs: dict[str, PatternPack]) -> dict[str, str]:
    out: dict[str, str] = {}
    for cid, pack in packs.items():
        for rid in pack.source_rule_ids:
            out[rid] = cid
        out[cid] = cid
    return out
