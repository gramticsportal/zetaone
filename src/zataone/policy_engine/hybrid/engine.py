# zataone Phase B HybridEngine — lexical + NLP + vision; replaces PolicyEngine when flagged

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from zataone.policy_engine.hybrid.flags import (
    ALWAYS_INCLUDE_CATEGORIES,
    hybrid_all_packs,
    hybrid_nlp_enabled,
    hybrid_retrieval_top_k,
)
from zataone.policy_engine.hybrid.lexical import match_lexical, match_vision
from zataone.policy_engine.hybrid.nlp import HybridNLPScorer
from zataone.policy_engine.hybrid.pack_loader import (
    PatternPack,
    build_rule_to_canonical,
    load_pattern_packs,
)
from zataone.schemas.violation import Violation as ViolationSchema

logger = logging.getLogger(__name__)


@dataclass
class HybridSignal:
    """Matcher signal emitted alongside violations (persisted like extractor signals)."""

    signal_id: str
    signal_type: str
    source_model: str
    confidence: float
    raw_data: dict
    bounding_box: None = None
    extractor_id: str = "hybrid_engine"


@dataclass
class HybridEvalResult:
    violations: list[ViolationSchema] = field(default_factory=list)
    signals: list[HybridSignal] = field(default_factory=list)
    shortlisted_canonical_ids: list[str] = field(default_factory=list)
    nlp_backend: str | None = None
    packs_evaluated: int = 0


class HybridEngine:
    """
    Deterministic hybrid evaluator:
      BM25/rule shortlist (under-filter) → pattern packs (phrase/regex/term/context/exceptions)
      + vision confidence gating + optional MiniLM/BoW NLP similarity.

    Duck-types PolicyEngine.evaluate(); also exposes evaluate_full() with hybrid signals.
    """

    def __init__(self) -> None:
        self._packs: dict[str, PatternPack] = load_pattern_packs(approved_only=True)
        self._rule_to_canonical = build_rule_to_canonical(self._packs)
        self._nlp: HybridNLPScorer | None = None
        self._last_result = HybridEvalResult()
        if hybrid_nlp_enabled():
            try:
                self._nlp = HybridNLPScorer()
            except Exception:
                logger.exception("hybrid NLP scorer init failed; lexical-only mode")

    @property
    def pack_count(self) -> int:
        return len(self._packs)

    @property
    def last_result(self) -> HybridEvalResult:
        return self._last_result

    def load_policy_pack(self, *args: Any, **kwargs: Any) -> None:
        """No-op compatibility with PolicyEngine.load_policy_pack."""
        return None

    def _document_text(self, signals: list[Any], document: Any | None) -> str:
        parts: list[str] = []
        if document is not None:
            nt = getattr(document, "normalized_text", None) or ""
            if nt:
                parts.append(str(nt))
            for scene in getattr(document, "scene_descriptions", None) or []:
                parts.append(str(scene))
        if not parts:
            for s in signals:
                raw = getattr(s, "raw_data", None) or {}
                if isinstance(raw, dict):
                    for k in ("text", "ocr_text", "transcript", "inspection"):
                        if raw.get(k):
                            parts.append(str(raw[k]))
                val = getattr(s, "value", None)
                if isinstance(val, dict) and val.get("text"):
                    parts.append(str(val["text"]))
                elif isinstance(val, str) and val.strip():
                    parts.append(val)
        return "\n".join(parts)[:50000]

    def _vision_signals(self, signals: list[Any]) -> list[Any]:
        out = []
        for s in signals:
            st = str(getattr(s, "signal_type", "") or "").lower()
            raw = getattr(s, "raw_data", None) or {}
            if "vision" in st or (isinstance(raw, dict) and raw.get("label")):
                out.append(s)
        return out

    def _shortlist_canonical_ids(
        self,
        active_rule_ids: set[str] | list[str] | None,
        document_text: str,
    ) -> list[str]:
        """Pack shortlist for lexical(/NLP) matching.

        Default: all approved packs. Optional under-filter when
        ZATAONE_HYBRID_ALL_PACKS=0: active rules ∪ always-include ∪ token pad.
        """
        if hybrid_all_packs() and active_rule_ids is None:
            return sorted(self._packs.keys())

        selected: set[str] = set()

        if active_rule_ids is not None:
            for rid in active_rule_ids:
                cid = self._rule_to_canonical.get(str(rid))
                if cid and cid in self._packs:
                    selected.add(cid)

        # Always-include critical categories
        for cid, pack in self._packs.items():
            if pack.category_id in ALWAYS_INCLUDE_CATEGORIES:
                selected.add(cid)

        # If still thin, pad with packs whose prototypes share tokens with the doc
        k = hybrid_retrieval_top_k()
        if len(selected) < max(12, k // 2):
            tokens = set(re_tokens(document_text))
            scored: list[tuple[float, str]] = []
            for cid, pack in self._packs.items():
                if cid in selected:
                    continue
                bag = " ".join(
                    pack.forbidden_phrases
                    + pack.forbidden_terms[:10]
                    + pack.embedding_prototypes[:2]
                ).lower()
                overlap = sum(1 for t in tokens if t in bag)
                if overlap:
                    scored.append((float(overlap), cid))
            scored.sort(reverse=True)
            for _, cid in scored[: max(0, k - len(selected))]:
                selected.add(cid)

        # Absolute floor: if empty, evaluate all packs (prefer under-filter)
        if not selected:
            return list(self._packs.keys())

        return sorted(selected)

    def evaluate(
        self,
        signals: list[Any],
        policy_pack_id: str | None = None,
        rules: list[Any] | None = None,
        document: Any | None = None,
        active_rule_ids: set[str] | list[str] | None = None,
    ) -> list[ViolationSchema]:
        result = self.evaluate_full(
            signals,
            document=document,
            active_rule_ids=active_rule_ids,
        )
        return result.violations

    def evaluate_full(
        self,
        signals: list[Any],
        *,
        document: Any | None = None,
        active_rule_ids: set[str] | list[str] | None = None,
    ) -> HybridEvalResult:
        text = self._document_text(signals, document)
        vision = self._vision_signals(signals)
        shortlist = self._shortlist_canonical_ids(active_rule_ids, text)

        violations: list[ViolationSchema] = []
        hybrid_signals: list[HybridSignal] = []
        nlp_backend = self._nlp.backend if self._nlp else None

        for cid in shortlist:
            pack = self._packs.get(cid)
            if pack is None:
                continue

            lexical_hits = match_lexical(text, pack)
            vision_hits = match_vision(vision, pack)
            nlp_hit = None
            if self._nlp is not None and hybrid_nlp_enabled():
                # NLP as support: only fire if lexical OR vision already suggestive,
                # OR as standalone when score is high and pack has prototypes.
                nlp_hit = self._nlp.score_pack(text, pack)

            # Decision: fire on strong lexical / vision; NLP alone needs higher bar
            fire_lexical = bool(lexical_hits)
            fire_vision = bool(vision_hits)
            fire_nlp = bool(
                nlp_hit
                and (
                    fire_lexical
                    or fire_vision
                    or float(nlp_hit["score"]) >= max(0.7, float(nlp_hit["threshold"]) + 0.1)
                )
            )
            if not (fire_lexical or fire_vision or fire_nlp):
                continue

            # Prefer attaching to an existing text/OCR signal when possible
            anchor_signal_id = _anchor_signal_id(signals, document)

            for hit in lexical_hits:
                sid = str(uuid.uuid4())
                hsig = HybridSignal(
                    signal_id=sid,
                    signal_type="hybrid_lexical_match",
                    source_model="hybrid_engine",
                    confidence=hit.confidence,
                    raw_data={
                        "matcher": hit.matcher,
                        "matched_text": hit.matched_text,
                        "canonical_id": pack.canonical_id,
                        "category_id": pack.category_id,
                        "clause_ids": pack.clause_ids,
                        "span_start": hit.span_start,
                        "span_end": hit.span_end,
                        "pattern_note": hit.pattern_note,
                        "anchor_signal_id": anchor_signal_id,
                    },
                )
                hybrid_signals.append(hsig)
                violations.append(
                    ViolationSchema(
                        signal_id=sid,
                        rule_id=pack.primary_rule_id,
                        violation_type="text_match",
                        severity=pack.severity_float,
                        evidence_data={
                            "evidence_type": "text_match",
                            "rule_name": pack.canonical_id,
                            "matched_text": hit.matched_text,
                            "matched_term": hit.matched_text,
                            "confidence": hit.confidence,
                            "signal_confidence": hit.confidence,
                            "matcher": hit.matcher,
                            "canonical_id": pack.canonical_id,
                            "category_id": pack.category_id,
                            "clause_ids": list(pack.clause_ids),
                            "hybrid": True,
                            "document_excerpt": text[:2000],
                            "matched_span": {
                                "start": hit.span_start,
                                "end": hit.span_end,
                            }
                            if hit.span_start is not None
                            else None,
                        },
                    )
                )

            for vh in vision_hits:
                s = vh["signal"]
                sid = str(getattr(s, "signal_id", "") or uuid.uuid4())
                # Also emit hybrid vision confirmation signal
                hsid = str(uuid.uuid4())
                hybrid_signals.append(
                    HybridSignal(
                        signal_id=hsid,
                        signal_type="hybrid_vision_match",
                        source_model="hybrid_engine",
                        confidence=float(vh["confidence"]),
                        raw_data={
                            "matcher": "vision_label",
                            "label": vh["label"],
                            "canonical_id": pack.canonical_id,
                            "vision_min_confidence": pack.vision_min_confidence,
                            "source_vision_signal_id": sid,
                        },
                    )
                )
                violations.append(
                    ViolationSchema(
                        signal_id=sid if _signal_id_known(signals, sid) else hsid,
                        rule_id=pack.primary_rule_id,
                        violation_type="vision_object",
                        severity=pack.severity_float,
                        evidence_data={
                            "evidence_type": "vision_object",
                            "rule_name": pack.canonical_id,
                            "label": vh["label"],
                            "confidence": float(vh["confidence"]),
                            "signal_confidence": float(vh["confidence"]),
                            "canonical_id": pack.canonical_id,
                            "category_id": pack.category_id,
                            "clause_ids": list(pack.clause_ids),
                            "hybrid": True,
                            "vision_min_confidence": pack.vision_min_confidence,
                            "bbox": (getattr(s, "raw_data", None) or {}).get("bbox"),
                            "model": (getattr(s, "raw_data", None) or {}).get(
                                "model", "grounding_dino"
                            ),
                        },
                    )
                )

            if fire_nlp and nlp_hit:
                sid = str(uuid.uuid4())
                hybrid_signals.append(
                    HybridSignal(
                        signal_id=sid,
                        signal_type="hybrid_nlp_match",
                        source_model="hybrid_engine",
                        confidence=float(nlp_hit["confidence"]),
                        raw_data={
                            "matcher": "nlp_embedding",
                            "backend": nlp_hit["backend"],
                            "score": nlp_hit["score"],
                            "prototype": nlp_hit["prototype"],
                            "canonical_id": pack.canonical_id,
                            "category_id": pack.category_id,
                        },
                    )
                )
                # Only add NLP violation if no lexical hit (avoid double-count) OR as support tag
                if not fire_lexical:
                    violations.append(
                        ViolationSchema(
                            signal_id=sid,
                            rule_id=pack.primary_rule_id,
                            violation_type="text_match",
                            severity=pack.severity_float * 0.85,
                            evidence_data={
                                "evidence_type": "text_match",
                                "rule_name": pack.canonical_id,
                                "matched_text": nlp_hit["prototype"][:120],
                                "matched_term": nlp_hit["prototype"][:120],
                                "confidence": float(nlp_hit["confidence"]),
                                "signal_confidence": float(nlp_hit["confidence"]),
                                "matcher": "nlp_embedding",
                                "nlp_backend": nlp_hit["backend"],
                                "nlp_score": nlp_hit["score"],
                                "canonical_id": pack.canonical_id,
                                "category_id": pack.category_id,
                                "clause_ids": list(pack.clause_ids),
                                "hybrid": True,
                                "document_excerpt": text[:2000],
                            },
                        )
                    )

        result = HybridEvalResult(
            violations=violations,
            signals=hybrid_signals,
            shortlisted_canonical_ids=shortlist,
            nlp_backend=nlp_backend,
            packs_evaluated=len(shortlist),
        )
        self._last_result = result
        logger.info(
            "hybrid evaluate: packs=%d shortlist=%d violations=%d signals=%d nlp=%s",
            len(self._packs),
            len(shortlist),
            len(violations),
            len(hybrid_signals),
            nlp_backend,
        )
        return result


def re_tokens(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9%]{3,}", (text or "").lower())


def _anchor_signal_id(signals: list[Any], document: Any | None) -> str | None:
    if document is not None:
        ids = getattr(document, "source_signal_ids", None) or []
        if ids:
            return str(ids[0])
    for s in signals:
        st = str(getattr(s, "signal_type", "") or "").lower()
        if any(x in st for x in ("text", "ocr", "keyword", "asr")):
            sid = getattr(s, "signal_id", None)
            if sid:
                return str(sid)
    if signals:
        sid = getattr(signals[0], "signal_id", None)
        return str(sid) if sid else None
    return None


def _signal_id_known(signals: list[Any], sid: str) -> bool:
    for s in signals:
        if str(getattr(s, "signal_id", "")) == sid:
            return True
    return False
