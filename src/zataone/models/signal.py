# zataone signal model

from __future__ import annotations
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Float, ForeignKey, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from zataone.storage.database import Base

if TYPE_CHECKING:
    from zataone.models.asset import Asset
    from zataone.models.evidence import Evidence
    from zataone.models.violation import Violation


class Signal(Base):
    """Signal model - extracted feature from an asset."""

    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    extractor_id = Column(String(128), nullable=False)
    signal_type = Column(String(64), nullable=False)
    value = Column(JSON, nullable=False, default=dict)
    confidence = Column(Float, nullable=False, default=0.0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="signals")
    evidence = relationship("Evidence", back_populates="signal", cascade="all, delete-orphan")
    violations = relationship("Violation", back_populates="signal", cascade="all, delete-orphan")