# zataone hybrid lexical matchers (phrase / regex / terms / context / exceptions)

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from zataone.policy_engine.hybrid.pack_loader import PatternPack


@dataclass
class LexicalHit:
    matcher: str  # phrase | regex | term
    matched_text: str
    confidence: float
    span_start: int | None = None
    span_end: int | None = None
    pattern_note: str | None = None


def _find_span(text: str, needle: str) -> tuple[int | None, int | None]:
    if not needle:
        return None, None
    idx = text.find(needle)
    if idx < 0:
        # case-insensitive fallback
        idx = text.lower().find(needle.lower())
    if idx < 0:
        return None, None
    return idx, idx + len(needle)


def _has_exception(text_l: str, pack: PatternPack) -> bool:
    for term in pack.exception_terms:
        if term and term in text_l:
            return True
    return False


def _context_ok(text_l: str, pack: PatternPack) -> bool:
    if not pack.requires_context_terms:
        return True
    return any(t in text_l for t in pack.requires_context_terms if t)


def match_lexical(text: str, pack: PatternPack) -> list[LexicalHit]:
    """
    Match pack against document text.
    Order: exceptions → context gate → phrases → regex → terms.
    Prefer phrase/regex; terms only if no stronger hit (or as supplement with lower conf).
    """
    if not text or not text.strip():
        return []
    text_l = text.lower()
    if _has_exception(text_l, pack):
        return []
    if not _context_ok(text_l, pack):
        return []

    hits: list[LexicalHit] = []

    for phrase in pack.forbidden_phrases:
        if phrase and phrase in text_l:
            start, end = _find_span(text_l, phrase)
            hits.append(
                LexicalHit(
                    matcher="phrase",
                    matched_text=phrase,
                    confidence=0.92,
                    span_start=start,
                    span_end=end,
                )
            )

    for pat in pack.forbidden_patterns:
        pattern = pat.get("pattern") if isinstance(pat, dict) else None
        if not pattern:
            continue
        try:
            m = re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL)
        except re.error:
            continue
        if m:
            hits.append(
                LexicalHit(
                    matcher="regex",
                    matched_text=m.group(0)[:200],
                    confidence=float(pat.get("confidence") or 0.88),
                    span_start=m.start(),
                    span_end=m.end(),
                    pattern_note=str(pat.get("note") or ""),
                )
            )

    # Terms: only add if no phrase/regex hit, to reduce noise
    if not hits:
        for term in pack.forbidden_terms:
            if not term or len(term) < 3 and "%" not in term:
                continue
            # word-ish boundary for short tokens
            if len(term) <= 4 and "%" not in term:
                if not re.search(rf"\b{re.escape(term)}\b", text_l):
                    continue
            elif term not in text_l:
                continue
            start, end = _find_span(text_l, term)
            hits.append(
                LexicalHit(
                    matcher="term",
                    matched_text=term,
                    confidence=0.72,
                    span_start=start,
                    span_end=end,
                )
            )
            if len(hits) >= 3:
                break

    # Deduplicate by matched_text
    seen: set[str] = set()
    uniq: list[LexicalHit] = []
    for h in hits:
        key = f"{h.matcher}:{h.matched_text.lower()}"
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    return uniq


def match_vision(
    vision_signals: list[Any],
    pack: PatternPack,
) -> list[dict[str, Any]]:
    """Return vision signal hits that meet pack label + min confidence."""
    if not pack.vision_labels:
        return []
    allowed = {l.lower() for l in pack.vision_labels}
    min_c = float(pack.vision_min_confidence or 0.55)
    out: list[dict[str, Any]] = []
    for s in vision_signals:
        raw = getattr(s, "raw_data", None) or {}
        label = str(raw.get("label") or "").strip().lower()
        conf = float(getattr(s, "confidence", 0.0) or raw.get("confidence") or 0.0)
        if label in allowed and conf >= min_c:
            out.append({"signal": s, "label": label, "confidence": conf})
    return out
