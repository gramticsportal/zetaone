# zataone hybrid lexical matchers (phrase / regex / terms / context / exceptions)

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from zataone.policy_engine.hybrid.pack_loader import (
    PatternPack,
    load_class_predicates,
    load_confidence_table,
    load_qualifiers,
    resolve_patterns_root,
)
from zataone.policy_engine.negation import negation_cue_for_span, term_is_inherently_negative
from zataone.policy_engine.predicates import evaluate as evaluate_predicate
from zataone.policy_engine.text_norm import normalize_term, normalize_with_map

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
    # Exactly what the creative said at this span. Differs from `matched_text` when the
    # advertiser obfuscated — the rule fired on "cure", the ad published "c-u-r-e" — and
    # evidence has to quote the ad, not the rule.
    source_text: str | None = None
    # Negation cue covering this hit, when one does. Recorded rather than silently
    # dropped so the audit trail can show the claim was read and found negated.
    negated_by: str | None = None


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


def _confidence(pack: PatternPack, matcher: str, default: float) -> float:
    """Measured confidence for this pack and matcher, or the shipped constant.

    The constants are one number per matcher type for all 54 packs, and the dev split says
    that is not true of them: the same regex confidence of 0.88 covers a pack that is right
    61% of the time and one that is right on none of its 29 hits.
    """
    root = resolve_patterns_root()
    if root is None:
        return default
    table = load_confidence_table(root.parent)
    return table.get(pack.canonical_id, {}).get(matcher, default)


def _has_exception(text_light: str, pack: PatternPack) -> bool:
    """Exceptions are read from lightly folded text — see normalize_with_map."""
    for term in pack.exception_terms:
        folded = normalize_term(term, aggressive=False)
        if folded and folded in text_light:
            return True
    return False


def _context_ok(text_l: str, pack: PatternPack) -> bool:
    if not pack.requires_context_terms:
        return True
    folded = [normalize_term(t) for t in pack.requires_context_terms]
    return any(t in text_l for t in folded if t)


def _licensed_by(text: str, hit: LexicalHit, pack: PatternPack) -> str | None:
    """Return the qualifier class licensing this hit, or None.

    `text` and the hit span are in original coordinates; the window is cut from the
    original and folded lightly, so an obfuscated disclaimer cannot license a claim.

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
    window = normalize_with_map(window, aggressive=False).text
    alternative, mandatory = load_class_predicates(root.parent)
    for class_id in pack.qualifier_classes:
        # A class with mandatory predicates licenses nothing until they hold, however
        # convincing its wording. Reg Z wants the rate, not the letters APR.
        required = mandatory.get(class_id)
        if required and not all(evaluate_predicate(name, window) for name in required):
            continue
        if any(pattern.search(window) for pattern in classes.get(class_id, [])):
            return class_id
        # Structural satisfaction: a stated rate, an age that is actually >= 21.
        if any(evaluate_predicate(name, window) for name in alternative.get(class_id, [])):
            return class_id
        # Mandatory predicates held and the class declared no patterns of its own.
        if required and not classes.get(class_id):
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
    # Match against folded text so homoglyphs, digit substitutions, injected separators
    # and zero-width padding cannot hide a trigger. Spans are mapped back before return.
    norm = normalize_with_map(text)
    text_l = norm.text
    if not text_l.strip():
        return []
    if _has_exception(normalize_with_map(text, aggressive=False).text, pack):
        return []
    if not _context_ok(text_l, pack):
        return []

    hits: list[LexicalHit] = []

    for phrase in pack.forbidden_phrases:
        folded = normalize_term(phrase)
        if not folded:
            continue
        start, end = _find_span(text_l, folded)
        if start is not None:
            hits.append(
                LexicalHit(
                    matcher="phrase",
                    matched_text=phrase,
                    confidence=_confidence(pack, "phrase", 0.92),
                    span_start=start,
                    span_end=end,
                )
            )

    for pat in pack.forbidden_patterns:
        pattern = pat.get("pattern") if isinstance(pat, dict) else None
        if not pattern:
            continue
        try:
            m = re.search(pattern, text_l, flags=re.IGNORECASE | re.DOTALL)
        except re.error:
            continue
        if m:
            hits.append(
                LexicalHit(
                    matcher="regex",
                    matched_text=m.group(0)[:200],
                    confidence=_confidence(pack, "regex", float(pat.get("confidence") or 0.88)),
                    span_start=m.start(),
                    span_end=m.end(),
                    pattern_note=str(pat.get("note") or ""),
                )
            )

    # Terms: only add if no phrase/regex hit, to reduce noise
    if not hits:
        for term in pack.forbidden_terms:
            folded = normalize_term(term)
            if not folded or len(folded) < 3 and "%" not in folded:
                continue
            start, end = _find_span(text_l, folded)
            if start is None:
                continue
            hits.append(
                LexicalHit(
                    matcher="term",
                    matched_text=term,
                    confidence=_confidence(pack, "term", 0.72),
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

    # Back to original coordinates first, so evidence quotes the creative as published
    # and the qualifier window is cut from the text the reader actually saw.
    for h in uniq:
        if h.span_start is None:
            continue
        o_start, o_end = norm.to_original_span(h.span_start, h.span_end or h.span_start)
        h.span_start, h.span_end = o_start, o_end
        h.source_text = text[o_start:o_end]

    for h in uniq:
        h.licensed_by = _licensed_by(text, h, pack)

    # Only for packs whose trigger is a claim of benefit — negating "no prescription
    # needed" or "we do not rent to families" states the violation rather than withdrawing
    # it. Read on the original text, since spans are now in original coordinates and the
    # cue patterns already tolerate curly apostrophes ("doesn’t"). Deliberately not folded
    # aggressively: "n0t a cure" should not buy an exoneration the reader cannot see.
    if pack.negation_sensitive:
        for h in uniq:
            if h.span_start is None or term_is_inherently_negative(h.matched_text):
                continue
            h.negated_by = negation_cue_for_span(text, h.span_start, h.span_end or h.span_start)

    if drop_licensed:
        return [h for h in uniq if not h.licensed_by and not h.negated_by]
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
