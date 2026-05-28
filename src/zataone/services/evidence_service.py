# zataone evidence persistence service

from __future__ import annotations
import uuid
from typing import Any

from sqlalchemy.orm import Session

from zataone.models import Evidence as EvidenceModel


class EvidenceService:
    """Evidence persistence service. Creates explicit evidence graph entries."""

    def generate(
        self,
        signals: list[Any],
        violations: list[Any],
    ) -> dict[str, Any]:
        """
        Generate evidence bundle from signals and violations.

        Violations from PolicyEngine already contain evidence.
        Returns a bundle for the verdict service.
        """
        return {
            "signals": signals,
            "violations": violations,
        }

    def persist_evidence(
        self,
        session: Session,
        asset_id: uuid.UUID,
        signal_records: list[Any],
        violation_records: list[Any],
    ) -> list[EvidenceModel]:
        """
        Create Evidence rows linking each violation to its signal.

        Each Evidence row includes: asset_id, signal_id, violation_id, rule_id, evidence_data.
        Evidence references both signal and violation for FK linkage integrity.

        Args:
            session: DB session
            asset_id: Asset UUID
            signal_records: Persisted Signal models
            violation_records: Persisted Violation models (from ViolationService.persist_violations)

        Returns:
            List of persisted Evidence models
        """
        persisted = []
        for v_rec in violation_records:
            evidence_data = dict(getattr(v_rec, "evidence_data", {}))
            model = EvidenceModel(
                asset_id=asset_id,
                signal_id=v_rec.signal_id,
                violation_id=v_rec.id,
                rule_id=v_rec.rule_id,
                evidence_data=evidence_data,
                content=evidence_data,  # backward compat with content column
            )
            session.add(model)
            session.flush()
            persisted.append(model)
        return persisted
