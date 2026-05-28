# zataone evidence model

from __future__ import annotations
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from zataone.storage.database import Base

if TYPE_CHECKING:
    from zataone.models.asset import Asset
    from zataone.models.signal import Signal
    from zataone.models.violation import Violation


class Evidence(Base):
    """Evidence model - explicit graph entry linking signal and violation."""

    __tablename__ = "evidence"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    signal_id = Column(UUID(as_uuid=True), ForeignKey("signals.id"), nullable=False)
    violation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("violations.id"),
        nullable=False,
    )
    rule_id = Column(String(128), nullable=False)
    evidence_data = Column(JSON, nullable=False, default=dict)
    content = Column(JSON, nullable=True)  # deprecated, use evidence_data; kept for backward compat
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="evidence")
    signal = relationship("Signal", back_populates="evidence")
    violation = relationship("Violation", back_populates="evidence")