# zataone hybrid lexical matchers (phrase / regex / terms / context / exceptions)

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from zataone.policy_engine.hybrid.pack_loader import (
    PatternPack,
    load_qualifiers,
    resolve_patterns_root,
)

# How far from the trigger a qualifier may sit and still license it. Ad copy in the corpus
# has a median length of 49 characters and a 95th percentile of 149, so for nearly all
# single ads this is the whole text. It matters on landing pages, where it stops a footer
# disclaimer from licensing a headline claim it is nowhere near.
QUALIFIER_WINDOW = 240


@dataclass
class LexicalHit:
    matcher: str  # phrase | regex | term
    matched_text: str
    confidence: float
    span_start: int | None = None
    span_end: int | None = None
    pattern_note: str | None = None
    # Qualifier class that licensed this hit, if any. Populated so an audit trail can show
    # why a trigger did not become a violation, not just that it didn't.
    licensed_by: str | None = None


@lru_cache(maxsize=8192)
def _boundary_re(needle: str) -> re.Pattern[str]:
    """Match `needle` only as a whole token.

    Plain substring matching made the pack term "elect" flag "in select areas" and
    "ELECTROLYTES: 2 1/2X THE LEADING SPORTS DRINK" as paid political advertising. \\b is
    the wrong tool here because triggers include things like "#ad" and "100%", where the
    edge character is not a word character and \\b would never match; lookarounds for word
    characters give the same protection without caring what the trigger starts with.
    """
    return re.compile(rf"(?<!\w){re.escape(needle)}(?!\w)", re.IGNORECASE)


def _find_span(text: str, needle: str) -> tuple[int | None, int | None]:
    if not needle:
        return None, None
    m = _boundary_re(needle).search(text)
    return (m.start(), m.end()) if m else (None, None)


def _has_exception(text_l: str, pack: PatternPack) -> bool:
    for term in pack.exception_terms:
        if term and term in text_l:
            return True
    return False


def _context_ok(text_l: str, pack: PatternPack) -> bool:
    if not pack.requires_context_terms:
        return True
    return any(t in text_l for t in pack.requires_context_terms if t)


def _licensed_by(text: str, hit: LexicalHit, pack: PatternPack) -> str | None:
    """Return the qualifier class licensing this hit, or None.

    Absolute packs are never licensed: no disclaimer makes a disease-cure claim or a
    counterfeit-goods ad lawful, so they short-circuit before any pattern runs.
    """
    if pack.is_absolute:
        return None
    root = resolve_patterns_root()
    if root is None:
        return None
    classes, _ = load_qualifiers(root.parent)
    if hit.span_start is None:
        window = text
    else:
        lo = max(0, hit.span_start - QUALIFIER_WINDOW)
        hi = min(len(text), (hit.span_end or hit.span_start) + QUALIFIER_WINDOW)
        window = text[lo:hi]
    for class_id in pack.qualifier_classes:
        for pattern in classes.get(class_id, []):
            if pattern.search(window):
                return class_id
    return None


def match_lexical(
    text: str,
    pack: PatternPack,
    *,
    drop_licensed: bool = True,
) -> list[LexicalHit]:
    """
    Match pack against document text.
    Order: exceptions → context gate → phrases → regex → terms → qualifier gate.
    Prefer phrase/regex; terms only if no stronger hit (or as supplement with lower conf).

    A trigger on its own does not make a violation. 85% of the compliant minimal pairs
    contain the same trigger as the violation they pair with, so the qualifier gate is what
    actually separates them: a hit survives only if the disclosure, scope or substantiation
    that would license the claim is missing. Pass drop_licensed=False to keep licensed hits
    with `licensed_by` set, which is what the audit trail and eval harness use to show why
    something was cleared.
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
        if not phrase:
            continue
        start, end = _find_span(text_l, phrase)
        if start is not None:
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
            start, end = _find_span(text_l, term)
            if start is None:
                continue
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

    for h in uniq:
        h.licensed_by = _licensed_by(text, h, pack)
    return [h for h in uniq if not h.licensed_by] if drop_licensed else uniq


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
