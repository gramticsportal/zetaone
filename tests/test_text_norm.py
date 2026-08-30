# -*- coding: utf-8 -*-
"""Normalization must fold evasions without corrupting the tokens packs match on."""

from __future__ import annotations

import pytest

from zataone.policy_engine.text_norm import normalize_term, normalize_with_map


def norm(text: str) -> str:
    return normalize_with_map(text).text


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Miracle cure guaranteed", "miracle cure guaranteed"),
        ("сure cancer", "cure cancer"),          # Cyrillic es
        ("оnly оne", "only one"),                # Cyrillic o
        ("cur3 cancer", "cure cancer"),                # digit substitution
        ("c-u-r-e cancer", "cure cancer"),             # separator injection
        ("c.u.r.e cancer", "cure cancer"),
        ("c u r e cancer", "cure cancer"),
        ("cu​re cancer", "cure cancer"),          # zero-width space
        ("cu­re cancer", "cure cancer"),          # soft hyphen
        ("café naïve", "cafe naive"),        # accents
        ("ｃure", "cure"),                          # fullwidth c
    ],
)
def test_evasions_fold(raw: str, expected: str) -> None:
    assert norm(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "$10,000 guaranteed",   # currency: no letter adjoins the digits
        "100% effective",
        "18+ only",
        "#ad sponsored",
        "t-shirt",              # real hyphenated word, not a letter run
        "e-mail",
        "21+ age gate",
    ],
)
def test_pack_tokens_survive(raw: str) -> None:
    """Packs match on these literally; folding them would break real rules."""
    assert norm(raw) == raw.lower()


def test_ordinary_doubles_survive() -> None:
    # Collapsing runs to one character would give "guaranted".
    assert norm("guaranteeeed results") == "guaranteed results"
    assert norm("free shipping") == "free shipping"


@pytest.mark.parametrize(
    "raw",
    ["$10,000", "1,000,000 users", "0.000 APR", "24.99% APR", "1000 free spins"],
)
def test_digit_runs_are_never_collapsed(raw: str) -> None:
    """Repeat-folding digits would rewrite the numbers the financial packs read."""
    assert norm(raw) == raw.lower()


def test_offsets_map_back_to_original() -> None:
    raw = "Buy c-u-r-e now"
    n = normalize_with_map(raw)
    assert n.text == "buy cure now"
    start = n.text.index("cure")
    o_start, o_end = n.to_original_span(start, start + len("cure"))
    assert raw[o_start:o_end] == "c-u-r-e"


def test_offsets_map_back_across_invisible_characters() -> None:
    raw = "take cu​re daily"
    n = normalize_with_map(raw)
    start = n.text.index("cure")
    o_start, o_end = n.to_original_span(start, start + len("cure"))
    assert raw[o_start:o_end] == "cu​re"


def test_offsets_never_exceed_original() -> None:
    raw = "cu​​re"
    n = normalize_with_map(raw)
    o_start, o_end = n.to_original_span(0, len(n.text))
    assert 0 <= o_start <= o_end <= len(raw)


def test_empty_and_whitespace() -> None:
    assert norm("") == ""
    assert norm("   ") == " "
    assert normalize_with_map("").to_original_span(0, 0) == (0, 0)


def test_idempotent() -> None:
    once = norm("сur3  c-a-n-c-e-r")
    assert norm(once) == once


def test_normalize_term_matches_document_folding() -> None:
    """A pack term and the copy it should catch must fold to the same string."""
    assert normalize_term("cure") in norm("cur3 cancer")
    assert normalize_term("FDA Approved") == "fda approved"
    assert normalize_term("100%") == "100%"
