# zataone deterministic text normalization for matching

"""Fold the ways ad copy is written to dodge a literal matcher.

The lexical matcher used to run against a bare `text.lower()`, so every one of these
walked straight through it:

    "сure"      Cyrillic с (U+0441), renders identically to ASCII c
    "cur3"      digit substitution
    "c-u-r-e"   separator injection
    "cu​re"      zero-width space between u and r
    "cuuure"    character padding

None of these are hypothetical: evading keyword filters is standard practice in the
categories this engine exists to police. Matching normalized text closes them.

Spans are the reason this returns an offset map rather than just a string. Evidence has
to quote the creative as published — an offset into a folded string would highlight the
wrong characters, or none, once folding changed the length. `offsets[i]` is the index in
the original text that produced `normalized[i]`, so a match found in normalized space can
always be reported in original space.

Normalization is idempotent and lossy in one direction only: it never invents characters,
so a term that matches normalized text had a real counterpart in the original.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

# Latin lookalikes from other scripts. Restricted to characters that actually render as
# the Latin letter in common fonts — folding anything looser would merge distinct words.
_CONFUSABLES = {
    # Cyrillic
    "а": "a", "в": "b", "с": "c", "е": "e", "ѕ": "s", "і": "i", "ј": "j",
    "к": "k", "м": "m", "н": "h", "о": "o", "р": "p", "т": "t", "у": "y",
    "х": "x", "ԁ": "d", "ɡ": "g", "ь": "b",
    # Greek
    "α": "a", "β": "b", "ε": "e", "ι": "i", "κ": "k", "ο": "o", "ρ": "p",
    "σ": "o", "τ": "t", "υ": "u", "χ": "x", "ν": "v", "μ": "u",
    # Fullwidth
    "ａ": "a", "ｂ": "b", "ｃ": "c", "ｄ": "d", "ｅ": "e", "ｆ": "f", "ｇ": "g",
    "ｈ": "h", "ｉ": "i", "ｊ": "j", "ｋ": "k", "ｌ": "l", "ｍ": "m", "ｎ": "n",
    "ｏ": "o", "ｐ": "p", "ｑ": "q", "ｒ": "r", "ｓ": "s", "ｔ": "t", "ｕ": "u",
    "ｖ": "v", "ｗ": "w", "ｘ": "x", "ｙ": "y", "ｚ": "z",
}

# Invisible characters used to break up a word without changing how it looks.
_INVISIBLE = frozenset(
    "​‌‍‎‏﻿­⁠᠎؜"
)

# Digit and symbol substitutions, applied only next to a letter. "1" alone is a quantity;
# "c1alis" is an evasion. Requiring a letter neighbour is what keeps "$10,000 guaranteed",
# "100%" and "18+" intact — all of which packs match on directly.
_LEET = {"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "$": "s", "@": "a", "|": "l"}

# Separators an evader puts between letters. Matching on single letters only, so real
# hyphenated words ("t-shirt", "e-mail") are untouched.
_SEP_RUN_RE = re.compile(r"(?<![0-9a-z])(?:[a-z][-_.*·•\s]){3,}[a-z](?![0-9a-z])")

# Letters only. Digits must never collapse: "$10,000" would become "$10,00", and this
# engine reads APRs, prices, percentages and age gates off exactly those digits.
_REPEAT_RE = re.compile(r"([a-z])\1{2,}")


@dataclass(frozen=True)
class NormalizedText:
    """Folded text plus a map back to the source."""

    text: str
    offsets: tuple[int, ...]
    original_length: int

    def to_original_span(self, start: int, end: int) -> tuple[int, int]:
        """Map a span in normalized space to the tightest covering span in the original."""
        if not self.offsets or start is None or end is None:
            return start, end
        start = max(0, min(start, len(self.offsets)))
        end = max(start, min(end, len(self.offsets)))
        if start >= len(self.offsets):
            return self.original_length, self.original_length
        o_start = self.offsets[start]
        # end is exclusive: take the character before it and step one past its source.
        o_end = self.offsets[end - 1] + 1 if end > start else o_start
        return o_start, max(o_end, o_start)


def _fold_char(ch: str) -> str:
    """Return the folded form of one character (may be empty or several characters)."""
    if ch in _INVISIBLE:
        return ""
    ch = _CONFUSABLES.get(ch, ch)
    # NFKD then drop combining marks: café -> cafe, ﬁ -> fi, ① -> 1.
    decomposed = unicodedata.normalize("NFKD", ch)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return (stripped or ch).lower()


def _is_letter(ch: str) -> bool:
    return "a" <= ch <= "z"


def _apply_leet(chars: list[str], offsets: list[int]) -> None:
    """Fold digit/symbol substitutions in place, only where a letter adjoins."""
    for i, ch in enumerate(chars):
        repl = _LEET.get(ch)
        if repl is None:
            continue
        prev_is_letter = i > 0 and _is_letter(chars[i - 1])
        next_is_letter = i + 1 < len(chars) and _is_letter(chars[i + 1])
        if prev_is_letter or next_is_letter:
            chars[i] = repl


def _drop_indices(chars: list[str], offsets: list[int], drop: set[int]) -> None:
    if not drop:
        return
    kept = [(c, o) for i, (c, o) in enumerate(zip(chars, offsets)) if i not in drop]
    chars[:] = [c for c, _ in kept]
    offsets[:] = [o for _, o in kept]


def _collapse_separator_runs(chars: list[str], offsets: list[int]) -> None:
    """"c-u-r-e" -> "cure", by dropping the separators only."""
    text = "".join(chars)
    drop: set[int] = set()
    for m in _SEP_RUN_RE.finditer(text):
        for i in range(m.start(), m.end()):
            if not _is_letter(text[i]):
                drop.add(i)
    _drop_indices(chars, offsets, drop)


def _collapse_repeats(chars: list[str], offsets: list[int]) -> None:
    """"cuuure" -> "cuure". Letter runs of 3+ fall back to 2, never to 1.

    Collapsing to 1 would corrupt ordinary doubles — "guaranteeeed" would become
    "guaranted" rather than "guaranteed" — so a padded word stays matchable only if the
    pack term itself has the doubled letter. Cheap insurance, not full coverage.
    """
    text = "".join(chars)
    drop: set[int] = set()
    for m in _REPEAT_RE.finditer(text):
        # keep the first two characters of the run
        for i in range(m.start() + 2, m.end()):
            drop.add(i)
    _drop_indices(chars, offsets, drop)


# One document is matched against every approved pack in turn, so without a cache the
# same text is folded ~150 times per request. Kept small on purpose: an entry holds an
# offset per character, so a handful of large documents is all that should ever be live.
@lru_cache(maxsize=16)
def normalize_with_map(text: str, *, aggressive: bool = True) -> NormalizedText:
    """Fold `text` for matching and keep a map back to the original offsets.

    Two levels, and which one to use depends on whether folding helps the advertiser:

    `aggressive=True` (triggers) also undoes leet substitution, injected separators and
    character padding. A trigger should be caught however it was disguised.

    `aggressive=False` (disclaimers, qualifiers, exceptions) undoes only what a reader
    would never notice — invisible characters, homoglyphs, accents, case, whitespace.
    These matchers *clear* a violation, so folding them aggressively would let
    "results m4y v4ry" buy a defence that no consumer could read. Obfuscated small print
    is not clear and conspicuous, and must not license a claim.
    """
    if not text:
        return NormalizedText("", (), 0)

    chars: list[str] = []
    offsets: list[int] = []
    for idx, ch in enumerate(text):
        folded = _fold_char(ch)
        for out in folded:
            chars.append(out)
            offsets.append(idx)

    if aggressive:
        _apply_leet(chars, offsets)
        _collapse_separator_runs(chars, offsets)
        _collapse_repeats(chars, offsets)

    # Whitespace runs collapse to a single space so `\s` in pack regexes behaves.
    squashed: list[str] = []
    squashed_offsets: list[int] = []
    for ch, off in zip(chars, offsets):
        if ch.isspace():
            if squashed and squashed[-1] == " ":
                continue
            squashed.append(" ")
            squashed_offsets.append(off)
        else:
            squashed.append(ch)
            squashed_offsets.append(off)

    return NormalizedText("".join(squashed), tuple(squashed_offsets), len(text))


@lru_cache(maxsize=8192)
def normalize_term(term: str, *, aggressive: bool = True) -> str:
    """Fold a pack term the same way, so both sides of a comparison agree."""
    return normalize_with_map(term, aggressive=aggressive).text.strip()
