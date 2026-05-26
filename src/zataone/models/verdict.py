# zataone verdict model

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Float, Integer, ForeignKey, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from zataone.storage.database import Base

if TYPE_CHECKING:
    from zataone.models.asset import Asset


class Verdict(Base):
    """Verdict model - compliance assessment result."""

    __tablename__ = "verdicts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    policy_pack_id = Column(String(255), nullable=True)
    status = Column(String(64), nullable=False)
    risk_score = Column(Float, nullable=False)
    processing_time_ms = Column(Integer, nullable=True)
    result = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    expiration_timestamp = Column(DateTime, nullable=True)

    asset = relationship("Asset", back_populates="verdicts")
