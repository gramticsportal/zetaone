# zataone policy corpus models

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PolicyVersion:
    version: str
    effective_date: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyClause:
    clause_id: str
    text: str
    modalities: list[str] = field(default_factory=lambda: ["text"])
    rule_ids: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PolicyPack:
    """Versioned policy pack loaded from YAML."""

    id: str
    platform: str
    jurisdiction: str
    version: PolicyVersion
    modalities: list[str] = field(default_factory=lambda: ["text"])
    clauses: list[PolicyClause] = field(default_factory=list)
    rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    source_path: str | None = None
    # sha256 of the source YAML bytes — makes any verdict reproducible against
    # the exact rule text that produced it, even after the YAML is edited.
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "jurisdiction": self.jurisdiction,
            "version": self.version.to_dict(),
            "modalities": list(self.modalities),
            "clauses": [c.to_dict() for c in self.clauses],
            "rule_count": len(self.rules),
            "source_path": self.source_path,
            "content_hash": self.content_hash,
        }
