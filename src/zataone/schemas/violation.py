# zataone violation schema

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class Violation:
    """Structured violation from policy evaluation. One per (signal, rule) pair."""

    signal_id: str
    rule_id: str
    violation_type: str
    severity: float
    evidence_data: dict
