# zataone audit service

from __future__ import annotations

import uuid
from typing import Any

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
        *,
        tenant_id: uuid.UUID | str | None = None,
        action: str | None = None,
        actor: dict[str, Any] | None = None,
        before_state: dict[str, Any] | None = None,
        after_state: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        correlation_id: uuid.UUID | None = None,
    ) -> AuditEvent:
        """Persist an AuditEvent. Returns the persisted AuditEvent model."""
        tid: uuid.UUID | None = None
        if tenant_id is not None:
            try:
                tid = uuid.UUID(str(tenant_id))
            except (ValueError, AttributeError):
                tid = None

        event = AuditEvent(
            asset_id=asset_id,
            verdict_id=verdict_id,
            tenant_id=tid,
            event_type=event_type,
            action=action or event_type,
            actor=actor,
            before_state=before_state,
            after_state=after_state,
            ip_address=ip_address,
            user_agent=user_agent,
            correlation_id=correlation_id,
            event_metadata=metadata or {},
        )
        session.add(event)
        session.flush()
        return event
