# zataone review decision model

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import String, Text, ForeignKey, Column, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy.orm import relationship

from zataone.storage.database import Base

if TYPE_CHECKING:
    from zataone.models.asset import Asset


class ReviewDecision(Base):
    """
    Recorded human decision on an asset's verdict.

    violation_feedback is the label payload for rule tuning:
      [{"violation_id": ..., "rule_id": ..., "assessment": "true_positive" | "false_positive",
        "note": ...}, ...]
    """

    __tablename__ = "review_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id = Column(
        UUID(as_uuid=True), ForeignKey("assets.id"), nullable=False, index=True
    )
    verdict_id = Column(UUID(as_uuid=True), ForeignKey("verdicts.id"), nullable=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    reviewer = Column(String(255), nullable=False)
    # approved | rejected | needs_changes
    decision = Column(String(32), nullable=False, index=True)
    reason = Column(Text, nullable=True)
    violation_feedback = Column(JSON, nullable=False, default=list)
    # human_review | appeal | platform_feedback
    source = Column(String(32), nullable=False, default="human_review")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    asset = relationship("Asset", back_populates="review_decisions")
