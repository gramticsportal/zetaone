# zataone violation persistence service

from __future__ import annotations
import uuid
from typing import Any

from sqlalchemy.orm import Session

from zataone.models import Violation as ViolationModel

_SEVERITY_WEIGHTS = {
    "LOW": 0.2,
    "MEDIUM": 0.4,
    "HIGH": 0.7,
    "CRITICAL": 1.0,
}


class ViolationService:
    """Violation persistence service. Stores violations linked to asset and signal."""

    def persist_violations(
        self,
        session: Session,
        asset_id: uuid.UUID,
        signal_records: list[Any],
        violations: list[Any],
    ) -> list[ViolationModel]:
        """
        Map violation evidence to signal_record ids, create Violation rows, return records.

        Args:
            session: DB session
            asset_id: Asset UUID
            signal_records: Persisted Signal models (evidence.signal_id maps to rec.id)
            violations: Violation objects from policy engine (dict or dataclass)

        Returns:
            List of persisted Violation models
        """
        signal_id_map = {str(rec.id): rec.id for rec in signal_records}

        persisted = []
        for v in violations:
            if hasattr(v, "signal_id") and hasattr(v, "violation_type"):
                sig_id = str(getattr(v, "signal_id", ""))
                persisted_signal_id = signal_id_map.get(sig_id)
                if persisted_signal_id is None:
                    continue
                rule_id = getattr(v, "rule_id", "")
                violation_type = getattr(v, "violation_type", "unknown")
                severity_val = getattr(v, "severity", 0.5)
                if isinstance(severity_val, (int, float)):
                    severity_float = float(severity_val)
                else:
                    severity_val = getattr(severity_val, "value", str(severity_val))
                    severity_float = _SEVERITY_WEIGHTS.get(str(severity_val), 0.5)
                evidence_data = dict(getattr(v, "evidence_data", {}))
                model = ViolationModel(
                    asset_id=asset_id,
                    signal_id=persisted_signal_id,
                    rule_id=rule_id,
                    violation_type=violation_type,
                    severity=severity_float,
                    evidence_data=evidence_data,
                )
                session.add(model)
                session.flush()
                persisted.append(model)
            else:
                rule_id = getattr(v, "rule_id", v.get("rule_id", ""))
                severity_val = getattr(v, "severity", v.get("severity", "HIGH"))
                if hasattr(severity_val, "value"):
                    severity_val = severity_val.value
                severity_float = _SEVERITY_WEIGHTS.get(str(severity_val), 0.5)
                evidence_list = getattr(v, "evidence", v.get("evidence", []))
                for ev in evidence_list:
                    sig_id = getattr(ev, "signal_id", ev.get("signal_id", ""))
                    persisted_signal_id = signal_id_map.get(str(sig_id))
                    if persisted_signal_id is None:
                        continue
                    violation_type = getattr(ev, "evidence_type", ev.get("evidence_type", "unknown"))
                    ev_data = ev.data if hasattr(ev, "data") else ev.get("data", {})
                    evidence_data = dict(ev_data) if ev_data else {}
                    model = ViolationModel(
                        asset_id=asset_id,
                        signal_id=persisted_signal_id,
                        rule_id=rule_id,
                        violation_type=violation_type,
                        severity=severity_float,
                        evidence_data=evidence_data,
                    )
                    session.add(model)
                    session.flush()
                    persisted.append(model)
        return persisted
