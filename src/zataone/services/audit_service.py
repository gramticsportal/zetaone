# zataone audit service

from __future__ import annotations
import uuid

from sqlalchemy.orm import Session

from zataone.models import AuditEvent


class AuditService:
    """Audit logging and trail service."""

    def persist_audit_event(
        self,
        session: Session,
        asset_id: uuid.UUID,
        verdict_id: uuid.UUID,
        event_type: str = "COMPLIANCE_CHECK",
        metadata: dict | None = None,
    ) -> AuditEvent:
        """Persist an AuditEvent. Returns the persisted AuditEvent model."""
        event = AuditEvent(
            asset_id=asset_id,
            verdict_id=verdict_id,
            event_type=event_type,
            event_metadata=metadata or {},
        )
        session.add(event)
        session.flush()
        return event
