# zetaone signal model

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Float, ForeignKey, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from zetaone.storage.database import Base

if TYPE_CHECKING:
    from zetaone.models.asset import Asset


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
