# zataone — load approved Phase A pattern packs

from __future__ import annotations

import logging
from dataclasses import dataclass, field
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
