# zetaone policy rule

from typing import Any


class Rule:
    """
    Policy rule definition. Loaded from configuration, never hard-coded.

    Attributes (from config): rule_id, name, severity, condition, evidence_template, etc.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize from configuration dict."""
        self._config = config or {}

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "Rule":
        """Create a Rule from configuration (YAML/JSON)."""
        return cls(config=config)

    def evaluate(self, signals: dict[str, Any]) -> bool:
        """
        Evaluate rule condition against extracted signals.
        Deterministic: same inputs always produce same result.
        """
        pass
