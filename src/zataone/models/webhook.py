# zataone webhook model

import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSON, UUID

from zataone.storage.database import Base


class Webhook(Base):
    """Registered webhook — receives POST on compliance events."""

    __tablename__ = "webhooks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    url = Column(String(2048), nullable=False)
    secret = Column(String(128), nullable=True)  # HMAC-SHA256 signing secret; never returned
    events = Column(JSON, nullable=False, default=list)   # ["verdict.completed", "verdict.flagged"]
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    last_triggered_at = Column(DateTime, nullable=True)
    last_status_code = Column(Integer, nullable=True)
