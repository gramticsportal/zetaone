# zataone policy evaluator

from __future__ import annotations
from typing import Any

from zataone.policy_engine.rule import Rule


class PolicyEvaluator:
    """
    Deterministic rule evaluator. Policies are configuration-driven.
    No hard-coded policy logic.
    """

    def evaluate_rule(self, rule: Rule, signals: dict[str, Any]) -> tuple[bool, dict[str, Any] | None]:
        """
        Evaluate a single rule against signals.

        Returns:
            (violated: bool, violation_context: dict | None)
        """
        pass

    def evaluate_rules(
        self, rules: list[Rule], signals: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """
        Evaluate all rules. Returns list of violations (empty if compliant).
        Deterministic and reproducible.
        """
        pass

    def explain(self, rule: Rule, signals: dict[str, Any]) -> str:
        """Return human-readable explanation of why rule passed or failed."""
        pass
