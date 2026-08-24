# zataone negation scope detection

"""Decide whether a matched trigger falls inside a negation.

The matcher scored these identically before this module existed:

    "This supplement is a cure for cancer."      -> 8 violations
    "This supplement is not a cure for cancer."  -> 8 violations

Opposite meanings, same verdict. The compliant minimal pairs are built by adding
qualification and hedging, so negation blindness lands squarely on the rows the engine
most needs to clear.

The algorithm is NegEx: find a negation cue, project a scope forward until a terminator,
and treat any trigger inside that scope as negated. It is a rule-based method from
clinical text and it transfers because ad copy has the same shape — short spans, explicit
cues, punctuation-bounded clauses.

**Negation does not always exonerate.** A whole class of prohibited claims *is* a
negation: "no risk", "zero side effects", "no credit check", "risk-free". Suppressing
those would delete real violations, so a trigger whose own wording carries a negation cue
is never suppressed — the rule already anticipated the negative form.
"""

from __future__ import annotations

import re
from functools import lru_cache

# Cues that negate what follows them.
_NEGATION_CUES = (
    "not", "no", "never", "none", "cannot", "can not", "cant", "can t",
    "won t", "wont", "does not", "doesn t", "doesnt", "did not", "didn t",
    "is not", "isn t", "isnt", "are not", "aren t", "arent", "was not", "wasn t",
    "will not", "shall not", "must not", "should not", "shouldn t",
    "without", "free of", "free from", "lacks", "lacking", "absent",
    "denies", "denied", "refuses", "unable to", "fails to", "failed to",
    "rather than", "instead of", "as opposed to", "other than",
    "nothing", "neither", "nor",
)

# Phrases that look like a cue but negate nothing: "not only X" asserts X.
_PSEUDO_NEGATIONS = (
    "not only", "not just", "not merely", "no doubt", "no wonder",
    "not to mention", "no less than", "none other than", "not surprisingly",
)

# A negation stops here: clause boundaries and contrastive conjunctions. "No artificial
# colours, but cures cancer" must not carry the negation across the comma.
_TERMINATORS = (
    "but", "however", "although", "though", "yet", "except", "unless",
    "while", "whereas", "still", "nevertheless", "nonetheless",
)

# How far a cue reaches when no terminator intervenes. Six tokens is the NegEx default and
# fits ad copy, whose median length in this corpus is around nine words.
SCOPE_TOKENS = 6

# Downsides. Negating one of these does not withdraw a claim, it makes a stronger one:
# "can't lose money" is a guaranteed-return claim, "no risks or side effects" is a safety
# claim. A double negative still asserts. Measured on the test split, this single guard
# accounts for most of what naive negation handling gets wrong on real ad copy.
_DOWNSIDE_RE = re.compile(
    r"(?<![a-z])("
    r"risks?|side[\s-]?effects?|lose|loses|losing|loss(?:es)?|lost"
    r"|fail(?:s|ed|ure)?|harm(?:ful)?|danger(?:ous)?|injur(?:y|ies)"
    r"|fees?|charges?|costs?|catch|obligations?|commitments?|strings?"
    r"|downside|drawbacks?|penalt(?:y|ies)|less|worse|wait(?:ing)?"
    r")(?![a-z])",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[a-z0-9%$]+|[.,;:!?]")

_CUE_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(c).replace(r"\ ", r"[\s'’-]*") for c in _NEGATION_CUES) + r")(?![a-z])",
    re.IGNORECASE,
)
_PSEUDO_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(p).replace(r"\ ", r"[\s'’-]*") for p in _PSEUDO_NEGATIONS) + r")(?![a-z])",
    re.IGNORECASE,
)


@lru_cache(maxsize=4096)
def term_is_inherently_negative(term: str) -> bool:
    """True when the rule's own wording is a negation, so negating it is the violation.

    "no risk", "zero side effects" and "risk-free" are prohibited *because* of the
    negative. Suppressing them as negated would delete the finding.
    """
    t = (term or "").lower()
    if not t:
        return False
    if re.search(r"(?<![a-z])(no|zero|without|free|non|never|nothing)(?![a-z])", t):
        return True
    return bool(re.search(r"[a-z]-free(?![a-z])|(?<![a-z])risk[\s-]*free", t))


@lru_cache(maxsize=256)
def _negated_char_ranges(text: str) -> tuple[tuple[int, int], ...]:
    """Character ranges covered by a negation scope."""
    if not text:
        return ()
    lowered = text.lower()

    pseudo = [(m.start(), m.end()) for m in _PSEUDO_RE.finditer(lowered)]

    ranges: list[tuple[int, int]] = []
    for cue in _CUE_RE.finditer(lowered):
        if any(ps <= cue.start() < pe for ps, pe in pseudo):
            continue

        scope_start = cue.end()
        tail = lowered[scope_start:]
        end = len(lowered)
        seen = 0
        for tok in _TOKEN_RE.finditer(tail):
            word = tok.group(0)
            if word in ".,;:!?" or word in _TERMINATORS:
                end = scope_start + tok.start()
                break
            seen += 1
            if seen >= SCOPE_TOKENS:
                end = scope_start + tok.end()
                break
        ranges.append((cue.start(), end))
    return tuple(ranges)


def negation_cue_for_span(text: str, start: int, end: int) -> str | None:
    """Return the cue negating this span, or None.

    Spans are in the same coordinate space as `text`. A span counts as negated when its
    start falls inside a scope — the cue precedes what it negates.
    """
    if not text or start is None:
        return None
    for lo, hi in _negated_char_ranges(text):
        if not (lo <= start < hi):
            continue
        # Negating a downside asserts a benefit rather than withdrawing a claim, so the
        # scope is not exonerating: "no risks", "can't lose", "no hidden fees".
        if _DOWNSIDE_RE.search(text[lo:hi]):
            return None
        return text[lo : min(hi, lo + 24)].strip() or None
    return None


def is_negated(text: str, start: int, end: int, matched_term: str = "") -> bool:
    """True when this hit sits inside a negation and the rule is not itself negative."""
    if matched_term and term_is_inherently_negative(matched_term):
        return False
    return negation_cue_for_span(text, start, end) is not None
