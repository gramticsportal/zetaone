# zetaone signal extraction service

import uuid
from typing import Any

from sqlalchemy.orm import Session

from zetaone.models import Signal as SignalModel


class SignalService:
    """Signal extraction orchestration and persistence service."""

    def persist_signals(
        self,
        session: Session,
        asset_id: uuid.UUID,
        signals: list[Any],
    ) -> list[SignalModel]:
        """Persist Signal objects. Returns list of persisted Signal models."""
        persisted = []
        for sig in signals:
            signal_id = getattr(sig, "signal_id", None) or uuid.uuid4()
            if isinstance(signal_id, str):
                signal_id = uuid.UUID(signal_id)
            raw_data = getattr(sig, "raw_data", {}) or {}
            if hasattr(raw_data, "copy"):
                value = dict(raw_data)
            else:
                value = raw_data if isinstance(raw_data, dict) else {}
            signal_type = str(getattr(sig, "signal_type", "unknown"))
            if hasattr(signal_type, "value"):
                signal_type = signal_type.value
            model = SignalModel(
                id=signal_id,
                asset_id=asset_id,
                extractor_id=getattr(sig, "source_model", "unknown"),
                signal_type=signal_type,
                value=value,
                confidence=float(getattr(sig, "confidence", 0.0)),
            )
            session.add(model)
            session.flush()
            persisted.append(model)
        return persisted
