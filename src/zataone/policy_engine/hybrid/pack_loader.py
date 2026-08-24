# zataone — load approved Phase A pattern packs

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from zataone.policy_engine.predicates import PREDICATES

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
    # Why this pack cannot be licensed, when that was an explicit decision rather than an
    # unwritten one. None on a pack with no qualifier classes means the gate is off by
    # omission — see load_qualifiers, which warns about exactly that case.
    absolute_reason: str | None = None
    # Highest `priority` among the corpus rules behind this pack. The corpus scores
    # regulators above platforms (95 for FTC/FDA/SEC, 54-72 for platform policy) so that a
    # statutory finding outranks a platform guideline when both fire.
    priority: int = 60
    # Whether negating this pack's trigger exonerates. False for most packs: "no
    # prescription needed" negates a safeguard and states the violation. See the
    # negation_sensitive section of qualifiers.yaml.
    negation_sensitive: bool = False

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
def load_class_predicates(patterns_root: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return (alternative, mandatory) predicate names per qualifier class.

    `predicates:` widens a class — another way to satisfy it, for phrasings the patterns
    do not cover. `requires_predicates:` narrows it — the class licenses nothing unless
    these hold, which is what a rule about a value rather than a word needs. Reg Z is the
    motivating case: the pattern `\\bapr\\b` happily clears "ask about our APR!", and the
    regulation is about the rate being stated.
    """
    path = patterns_root / "qualifiers.yaml"
    if not path.is_file():
        return {}, {}
    doc = yaml.safe_load(path.open(encoding="utf-8")) or {}
    alternative: dict[str, list[str]] = {}
    mandatory: dict[str, list[str]] = {}
    for entry in doc.get("classes") or []:
        cid = str(entry.get("id") or "")
        if not cid:
            continue
        alts = entry.get("predicates") or ([entry["predicate"]] if entry.get("predicate") else [])
        known_alts = [str(n) for n in alts if str(n) in PREDICATES]
        if known_alts:
            alternative[cid] = known_alts
        reqs = [str(n) for n in (entry.get("requires_predicates") or []) if str(n) in PREDICATES]
        if reqs:
            mandatory[cid] = reqs
    return alternative, mandatory


@lru_cache(maxsize=8)
def load_confidence_table(patterns_root: Path) -> dict[str, dict[str, float]]:
    """Return canonical_id -> matcher -> measured confidence.

    Written by ontology/tools/calibrate_pack_confidence.py from the dev split. Absent
    entries fall back to the shipped constants, so a missing file changes nothing.
    """
    path = patterns_root / "confidence.yaml"
    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.open(encoding="utf-8")) or {}
    out: dict[str, dict[str, float]] = {}
    for cid, matchers in (doc.get("packs") or {}).items():
        if not isinstance(matchers, dict):
            continue
        out[str(cid)] = {
            str(m): float(v) for m, v in matchers.items() if isinstance(v, (int, float))
        }
    return out


@lru_cache(maxsize=8)
def load_negation_sensitive(patterns_root: Path) -> frozenset[str]:
    """Canonical ids where a negated trigger should be cleared rather than reported."""
    path = patterns_root / "qualifiers.yaml"
    if not path.is_file():
        return frozenset()
    doc = yaml.safe_load(path.open(encoding="utf-8")) or {}
    return frozenset(
        str(entry.get("id"))
        for entry in (doc.get("negation_sensitive") or [])
        if entry.get("id")
    )


@lru_cache(maxsize=8)
def load_rule_priorities(ontology_root: Path) -> dict[str, int]:
    """Return corpus rule_id -> priority.

    Priority already exists on all 137 corpus rules and was not reaching the matcher, so
    a Meta guideline and an FTC statute produced indistinguishable violations.
    """
    corpus = ontology_root / "corpus"
    if not corpus.is_dir():
        return {}
    out: dict[str, int] = {}
    for path in sorted(corpus.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.open(encoding="utf-8")) or {}
        except Exception:  # a malformed corpus file must not take the matcher down
            logger.exception("pack_loader: could not read %s for priorities", path.name)
            continue
        for rule in doc.get("rules") or []:
            rid = str(rule.get("id") or "")
            pri = rule.get("priority")
            if rid and isinstance(pri, int):
                out[rid] = pri
    return out


@lru_cache(maxsize=8)
def load_absolute_reasons(patterns_root: Path) -> dict[str, str]:
    """Return canonical_id -> stated reason it cannot be licensed."""
    path = patterns_root / "qualifiers.yaml"
    if not path.is_file():
        return {}
    doc = yaml.safe_load(path.open(encoding="utf-8")) or {}
    out: dict[str, str] = {}
    for key in ("absolute", "unmodelled"):
        for entry in doc.get(key) or []:
            cid = str(entry.get("id") or "")
            if cid:
                out[cid] = str(entry.get("reason") or key)
    return out


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

    for entry in doc.get("classes") or []:
        cid = str(entry.get("id") or "")
        names = entry.get("predicates") or ([entry["predicate"]] if entry.get("predicate") else [])
        for name in names:
            if str(name) not in PREDICATES:
                logger.warning("qualifiers.yaml: %s names unknown predicate %r", cid, name)

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
    absolute_reasons = load_absolute_reasons(root.parent)
    # root is ontology/patterns/by_category; the corpus sits at ontology/corpus.
    priorities = load_rule_priorities(root.parent.parent)
    negation_sensitive = load_negation_sensitive(root.parent)

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
                absolute_reason=absolute_reasons.get(cid),
                priority=max(
                    (priorities[r] for r in (raw.get("source_rule_ids") or []) if r in priorities),
                    default=60,
                ),
                negation_sensitive=cid in negation_sensitive,
            )

    # A pack with no qualifier classes and no stated reason has its gate off by omission.
    # It will fire on every trigger it sees, with no way to be cleared, and nothing in the
    # data says whether that was intended.
    unclassified = sorted(
        cid for cid, p in packs.items() if not p.qualifier_classes and not p.absolute_reason
    )
    if unclassified:
        logger.warning(
            "hybrid pack_loader: %d pack(s) neither licensed nor declared absolute: %s",
            len(unclassified),
            ", ".join(unclassified),
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
