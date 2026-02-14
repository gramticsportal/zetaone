# zetaone evidence generation service

import uuid
from typing import Any

from sqlalchemy.orm import Session

from zetaone.models import Evidence as EvidenceModel


class EvidenceService:
    """Evidence generation, bundling, and persistence service."""

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
        evidence: dict[str, Any],
    ) -> list[EvidenceModel]:
        """
        Persist Evidence from evidence bundle.
        signal_records: persisted Signal models (order matches evidence["signals"])
        evidence: dict with "signals" and "violations"
        """
        signals = evidence.get("signals", [])
        violations = evidence.get("violations", [])
        signal_id_map = {}
        for sig, rec in zip(signals, signal_records):
            sid = getattr(sig, "signal_id", None)
            if sid is not None:
                signal_id_map[str(sid)] = rec.id

        persisted = []
        for v in violations:
            rule_id = getattr(v, "rule_id", v.get("rule_id", ""))
            evidence_list = getattr(v, "evidence", v.get("evidence", []))
            for ev in evidence_list:
                sig_id = getattr(ev, "signal_id", ev.get("signal_id", ""))
                persisted_signal_id = signal_id_map.get(str(sig_id))
                if persisted_signal_id is None:
                    continue
                content = {}
                if hasattr(ev, "data"):
                    content = dict(ev.data) if ev.data else {}
                elif isinstance(ev, dict):
                    content = ev.get("data", ev)
                if hasattr(content, "copy"):
                    content = dict(content)
                model = EvidenceModel(
                    asset_id=asset_id,
                    signal_id=persisted_signal_id,
                    rule_id=rule_id,
                    content=content,
                )
                session.add(model)
                session.flush()
                persisted.append(model)
        return persisted
