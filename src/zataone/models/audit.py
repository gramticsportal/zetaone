# zataone audit model

from __future__ import annotations
import uuid
from datetime import datetime

from sqlalchemy import String, ForeignKey, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON

from zataone.storage.database import Base


class AuditEvent(Base):
    """AuditEvent model - audit trail for compliance processing."""

    __tablename__ = "audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    verdict_id = Column(UUID(as_uuid=True), ForeignKey("verdicts.id"), nullable=False)
    event_type = Column(String(64), nullable=False)
    event_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
