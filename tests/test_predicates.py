# -*- coding: utf-8 -*-
"""Structural predicates, and the qualifier semantics built on them."""

from __future__ import annotations

import pytest

from zataone.policy_engine.hybrid.lexical import match_lexical
from zataone.policy_engine.hybrid.pack_loader import PatternPack
from zataone.policy_engine.predicates import (
    age_gate_21,
    apr_figure_present,
    evaluate,
    quantified_claim_present,
    repayment_terms_present,
)


@pytest.mark.parametrize(
    "window,expected",
    [
        ("24.99% APR on all purchases", True),
        ("APR 7.5% for qualified buyers", True),
        ("annual percentage rate of 12.9%", True),
        ("Ask us about our low APR!", False),      # the advertisement, not the disclosure
        ("100% approval, no APR games", False),    # a proportion, not a rate
        ("0% for 12 months", False),               # no APR named
    ],
)
def test_apr_figure_present(window: str, expected: bool) -> None:
    assert apr_figure_present(window) is expected


@pytest.mark.parametrize(
    "window,expected",
    [
        ("21+ only", True),
        ("must be 25 years or older", True),
        ("18+ event", False),          # states 18, not 21
        ("for adults", False),
    ],
)
def test_age_gate_21(window: str, expected: bool) -> None:
    assert age_gate_21(window) is expected


def test_repayment_terms_needs_both_money_and_duration() -> None:
    assert repayment_terms_present("$199 per month for 36 months")
    assert not repayment_terms_present("$199 per month")
    assert not repayment_terms_present("36 months to pay")


def test_quantified_claim() -> None:
    assert quantified_claim_present("reduces wrinkles by 32% in 8 weeks")
    assert not quantified_claim_present("clinically proven to work")


def test_unknown_predicate_never_licenses() -> None:
    assert evaluate("no_such_predicate", "anything at all") is False


def _credit_pack() -> PatternPack:
    return PatternPack(
        canonical_id="finance.credit_advertising_trigger_terms",
        category_id="financial",
        severity="high",
        review_status="approved",
        forbidden_terms=["down payment"],
        qualifier_classes=["credit_terms_disclosure"],
    )


def test_mandatory_predicate_blocks_a_wording_only_disclosure() -> None:
    """The bare word "APR" used to license a credit ad. Reg Z wants the rate."""
    hits = match_lexical("Low down payment — ask about our APR!", _credit_pack())
    assert hits, "wording-only disclosure should no longer license the claim"


def test_mandatory_predicate_licenses_when_the_rate_is_stated() -> None:
    hits = match_lexical("Low down payment. 24.99% APR, finance charge applies.", _credit_pack())
    assert not hits, "a stated rate is a real Reg Z disclosure and should clear"
