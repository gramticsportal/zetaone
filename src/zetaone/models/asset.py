# zetaone asset model

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from zetaone.storage.database import Base

if TYPE_CHECKING:
    from zetaone.models.signal import Signal
    from zetaone.models.evidence import Evidence
    from zetaone.models.verdict import Verdict


class Asset(Base):
    """Asset model - input content for compliance check."""

    __tablename__ = "assets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    content_hash = Column(String(64), nullable=False)
    type = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    signals = relationship("Signal", back_populates="asset", cascade="all, delete-orphan")
    evidence = relationship("Evidence", back_populates="asset", cascade="all, delete-orphan")
    verdicts = relationship("Verdict", back_populates="asset", cascade="all, delete-orphan")
