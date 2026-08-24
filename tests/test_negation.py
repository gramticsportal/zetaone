# -*- coding: utf-8 -*-
"""Negation scope, and the cases where negating a claim IS the claim."""

from __future__ import annotations

import pytest

from zataone.policy_engine.hybrid.lexical import match_lexical
from zataone.policy_engine.hybrid.pack_loader import PatternPack
from zataone.policy_engine.negation import (
    is_negated,
    negation_cue_for_span,
    term_is_inherently_negative,
)


def cure_pack(**kw) -> PatternPack:
    base = dict(
        canonical_id="health.disease_cure_treatment_claims",
        category_id="health",
        severity="high",
        review_status="approved",
        forbidden_terms=["cure"],
        # Negation only exonerates for packs whose trigger is a benefit claim; this is one.
        negation_sensitive=True,
    )
    base.update(kw)
    return PatternPack(**base)


def span_of(text: str, needle: str) -> tuple[int, int]:
    i = text.lower().index(needle.lower())
    return i, i + len(needle)


@pytest.mark.parametrize(
    "text,needle",
    [
        ("This supplement is not a cure for cancer.", "cure"),
        ("We cannot guarantee any results.", "guarantee"),
        ("This does not treat any disease.", "treat"),
        ("Sold without any cure claims.", "cure"),
        ("It will never cure anything.", "cure"),
        ("This doesn’t cure cancer.", "cure"),      # curly apostrophe
    ],
)
def test_negated_claims_are_detected(text: str, needle: str) -> None:
    start, end = span_of(text, needle)
    assert is_negated(text, start, end, needle)


@pytest.mark.parametrize(
    "text,needle",
    [
        ("This supplement is a cure for cancer.", "cure"),
        ("Not only a cure, but a miracle.", "cure"),        # pseudo-negation
        ("No artificial colours, but cures cancer.", "cures"),  # terminator stops scope
        ("Guaranteed to cure cancer.", "cure"),
    ],
)
def test_unnegated_claims_are_not_suppressed(text: str, needle: str) -> None:
    start, end = span_of(text, needle)
    assert not is_negated(text, start, end, needle)


@pytest.mark.parametrize(
    "term", ["no risk", "zero side effects", "risk-free", "no credit check", "without fees"]
)
def test_inherently_negative_rules_are_never_suppressed(term: str) -> None:
    """These are prohibited *because* they are negations — suppressing deletes the finding."""
    assert term_is_inherently_negative(term)
    text = f"Invest today — {term}!"
    start, end = span_of(text, term)
    assert not is_negated(text, start, end, term)


def test_scope_does_not_cross_a_clause_boundary() -> None:
    text = "No artificial ingredients. This product cures cancer."
    start, end = span_of(text, "cures")
    assert negation_cue_for_span(text, start, end) is None


def test_matcher_clears_a_negated_claim_end_to_end() -> None:
    assert match_lexical("This supplement is a cure for cancer.", cure_pack())
    assert not match_lexical("This supplement is not a cure for cancer.", cure_pack())


def test_negation_is_recorded_not_silently_dropped() -> None:
    hits = match_lexical("This is not a cure.", cure_pack(), drop_licensed=False)
    assert hits and hits[0].negated_by, "audit trail must show why the hit was cleared"


def test_inherently_negative_pack_still_fires_end_to_end() -> None:
    p = cure_pack(canonical_id="finance.guaranteed_returns_or_risk_free", forbidden_terms=["no risk"])
    assert match_lexical("Crypto with no risk at all.", p)


def test_packs_are_not_negation_sensitive_by_default() -> None:
    """The safe default. "no prescription needed" must never be cleared as negated."""
    p = PatternPack(
        canonical_id="health.prescription_drug_promotion_restricted",
        category_id="health",
        severity="high",
        review_status="approved",
        forbidden_terms=["prescription"],
    )
    assert not p.negation_sensitive
    assert match_lexical("Buy Xanax online — no prescription needed.", p)


@pytest.mark.parametrize(
    "text,needle",
    [
        ("Invest now — you simply can't lose money.", "lose"),
        ("No risks or side effects whatsoever.", "effects"),
        ("Sign up today, no hidden fees.", "fees"),
    ],
)
def test_negating_a_downside_asserts_a_benefit(text: str, needle: str) -> None:
    """A double negative still makes a claim: "can't lose" is a guaranteed return."""
    start, end = span_of(text, needle)
    assert negation_cue_for_span(text, start, end) is None
