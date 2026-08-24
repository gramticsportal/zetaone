# -*- coding: utf-8 -*-
"""The matcher must see through obfuscation and still cite the published wording."""

from __future__ import annotations

import pytest

from zataone.policy_engine.hybrid.lexical import match_lexical
from zataone.policy_engine.hybrid.pack_loader import PatternPack


def pack(**kw) -> PatternPack:
    base = dict(
        canonical_id="health.disease_cure_treatment_claims",
        category_id="health",
        severity="high",
        review_status="approved",
        forbidden_terms=["cure"],
        forbidden_phrases=[],
        forbidden_patterns=[],
        requires_context_terms=[],
        exception_terms=[],
    )
    base.update(kw)
    return PatternPack(**base)


@pytest.mark.parametrize(
    "content",
    [
        "cure for cancer",
        "сure for cancer",       # Cyrillic es
        "cur3 for cancer",             # digit substitution
        "c-u-r-e for cancer",          # separator injection
        "cu​re for cancer",       # zero-width space
        "CURE for cancer",             # case
    ],
)
def test_obfuscated_triggers_are_caught(content: str) -> None:
    hits = match_lexical(content, pack())
    assert hits, f"missed obfuscated trigger in {content!r}"
    assert hits[0].matched_text == "cure"


def test_span_points_at_the_published_wording() -> None:
    content = "Buy c-u-r-e now"
    hits = match_lexical(content, pack())
    assert hits
    hit = hits[0]
    assert content[hit.span_start : hit.span_end] == "c-u-r-e"
    assert hit.source_text == "c-u-r-e"


def test_span_is_exact_for_unobfuscated_text() -> None:
    content = "a proven cure today"
    hits = match_lexical(content, pack())
    assert hits
    assert content[hits[0].span_start : hits[0].span_end] == "cure"


def test_context_gate_still_applies_after_folding() -> None:
    p = pack(requires_context_terms=["cancer"])
    assert match_lexical("cur3 for cancer", p)
    assert not match_lexical("cur3 for shoes", p)


def test_exception_clears_a_plainly_written_disclaimer() -> None:
    p = pack(exception_terms=["results may vary"])
    assert not match_lexical("cure — results may vary", p)
    # Invisible and homoglyph folding still applies: a reader sees this normally.
    assert not match_lexical("cure — results m​ay vary", p)


@pytest.mark.parametrize(
    "disclaimer",
    ["results m4y v4ry", "results m-a-y v-a-r-y", "results mayyyy vary"],
)
def test_obfuscated_disclaimer_cannot_license_a_claim(disclaimer: str) -> None:
    """Small print only counts if it is clear and conspicuous.

    Folding exceptions as hard as triggers would let an advertiser manufacture a defence
    out of text no consumer can read, so the exception matcher deliberately does not.
    """
    p = pack(exception_terms=["results may vary"])
    assert match_lexical(f"cure — {disclaimer}", p)


def test_phrase_matcher_folds() -> None:
    p = pack(forbidden_terms=[], forbidden_phrases=["fda approved"])
    hits = match_lexical("totally FDA-approved", p)
    assert not hits  # hyphen inside a real word pair is not a single-letter run
    hits = match_lexical("totally FDA approved", p)
    assert hits and hits[0].matcher == "phrase"


def test_regex_matcher_runs_on_folded_text() -> None:
    p = pack(
        forbidden_terms=[],
        forbidden_patterns=[{"pattern": r"\bcure[sd]?\b.{0,20}\bcancer\b", "confidence": 0.9}],
    )
    hits = match_lexical("cur3s advanced cancer", p)
    assert hits and hits[0].matcher == "regex"


def test_digits_are_not_folded_into_letters() -> None:
    """Financial packs read the numbers; folding them would rewrite the claim."""
    p = pack(forbidden_terms=["$10,000"])
    hits = match_lexical("earn $10,000 weekly", p)
    assert hits
    assert hits[0].source_text == "$10,000"


def test_empty_input_is_safe() -> None:
    assert match_lexical("", pack()) == []
    assert match_lexical("   ", pack()) == []
