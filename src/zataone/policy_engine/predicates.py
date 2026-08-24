# zataone structural predicates for the qualifier gate

"""Checks a regex cannot make, because they are about values rather than vocabulary.

Regulation is full of arithmetic that pattern matching can only pretend to see. TILA does
not require the letters "APR" near a credit trigger term — it requires the *rate*, stated
as a number. A pack matching the word "APR" clears "ask us about our APR!" and a pack
matching `\\d+%` clears "100% approval". Neither is the rule.

Predicates plug into the qualifier gate rather than sitting beside it, so a structural
licence produces the same `licensed_by` audit trail as a textual one, respects the same
window around the trigger, and is skipped for absolute packs exactly like a pattern is.

Each predicate answers one question about a window of text and nothing else. They are
deliberately conservative: a predicate that is unsure returns False, which leaves the
violation standing for a human to clear rather than clearing it automatically.
"""

from __future__ import annotations

import re
from typing import Callable

# A percentage that is a rate, not a proportion of customers. Requires a decimal or a
# small-to-plausible integer: "24.99% APR" and "7% APR" qualify, "100% approved" does not.
_RATE_RE = re.compile(
    r"(?<![\w.])(\d{1,2}(?:\.\d{1,3})?)\s*%\s*(?:apr|a\.p\.r\.|annual percentage rate)"
    r"|(?:apr|a\.p\.r\.|annual percentage rate)\D{0,20}?(\d{1,2}(?:\.\d{1,3})?)\s*%",
    re.IGNORECASE,
)

_CURRENCY_RE = re.compile(r"(?<![\w])\$\s?\d[\d,]*(?:\.\d{2})?", re.IGNORECASE)

_PERCENT_RE = re.compile(r"(?<![\w.])\d{1,3}(?:\.\d{1,3})?\s*%")

# "21+", "must be 21", "21 or older", "over 18". Captures the stated minimum age.
_AGE_RE = re.compile(
    r"(?<![\w])(\d{2})\s*\+"
    r"|(?:must be|aged?|over|at least|18|21)?\s*(?<![\w])(\d{2})\s*(?:\+|years? or older|or older|and over|and older)",
    re.IGNORECASE,
)

_TERM_LENGTH_RE = re.compile(
    r"(?<![\w])\d{1,3}\s*(?:month|months|mo|year|years|yr|yrs|week|weeks|day|days)(?![\w])",
    re.IGNORECASE,
)


def _stated_ages(window: str) -> list[int]:
    ages: list[int] = []
    for m in _AGE_RE.finditer(window):
        for group in m.groups():
            if group:
                try:
                    ages.append(int(group))
                except ValueError:
                    continue
    return ages


def apr_figure_present(window: str) -> bool:
    """A numeric annual percentage rate is stated, not merely the letters APR.

    Reg Z triggers on terms like a down payment or a monthly figure, and what it demands
    back is the rate itself. "Low APR!" is the advertisement, not the disclosure.
    """
    return bool(_RATE_RE.search(window))


def cost_figure_present(window: str) -> bool:
    """Some amount of money is named — a price, a fee, a payment."""
    return bool(_CURRENCY_RE.search(window))


def repayment_terms_present(window: str) -> bool:
    """A credit offer states both a cost and how long it runs for."""
    return bool(_CURRENCY_RE.search(window)) and bool(_TERM_LENGTH_RE.search(window))


def age_gate_18(window: str) -> bool:
    return any(age >= 18 for age in _stated_ages(window))


def age_gate_21(window: str) -> bool:
    return any(age >= 21 for age in _stated_ages(window))


def quantified_claim_present(window: str) -> bool:
    """The claim is pinned to a number rather than left at large.

    "Clinically proven to reduce wrinkles by 32% in 8 weeks" is checkable; "clinically
    proven to work" is not. This does not decide whether the number is true — only that
    the advertiser committed to one.
    """
    return bool(_PERCENT_RE.search(window) or _TERM_LENGTH_RE.search(window))


PREDICATES: dict[str, Callable[[str], bool]] = {
    "apr_figure_present": apr_figure_present,
    "cost_figure_present": cost_figure_present,
    "repayment_terms_present": repayment_terms_present,
    "age_gate_18": age_gate_18,
    "age_gate_21": age_gate_21,
    "quantified_claim_present": quantified_claim_present,
}


def evaluate(name: str, window: str) -> bool:
    """Run a named predicate. An unknown name never licenses anything."""
    fn = PREDICATES.get(name)
    return bool(fn and fn(window))
