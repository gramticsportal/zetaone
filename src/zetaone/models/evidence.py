# zetaone evidence model

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from zetaone.storage.database import Base

if TYPE_CHECKING:
    from zetaone.models.asset import Asset
    from zetaone.models.signal import Signal


class Evidence(Base):
    """Evidence model - supporting evidence for a rule violation."""

    __tablename__ = "evidence"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False)
    signal_id = Column(UUID(as_uuid=True), ForeignKey("signals.id"), nullable=False)
    rule_id = Column(String(128), nullable=False)
    content = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    asset = relationship("Asset", back_populates="evidence")
