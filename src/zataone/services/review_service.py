# zataone human review service

"""
Review queue + decision recording (the human half of the compliance cycle).

Assets enter review_state='pending_review' when the pipeline finishes with a
borderline / REVIEW_REQUIRED verdict or with degraded extraction. A recorded
decision becomes the authoritative final state and doubles as label data:
asset-level ground truth plus per-violation true/false-positive marks.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from zataone.models import (
    Asset as AssetModel,
    ReviewDecision,
    Verdict as VerdictModel,
)
from zataone.services.audit_service import AuditService

logger = logging.getLogger(__name__)

VALID_DECISIONS = ("approved", "rejected", "needs_changes")
VALID_SOURCES = ("human_review", "appeal", "platform_feedback")

_DECISION_TO_STATE = {
    "approved": "final_approved",
    "rejected": "final_rejected",
    "needs_changes": "final_needs_changes",
}


def review_state_for_verdict(verdict: dict[str, Any]) -> str | None:
    """
    Decide whether a completed pipeline verdict needs human review.

    pending_review when: borderline / REVIEW_REQUIRED / pending_advisory, high
    risk (likely_rejected — auto-flag, review optional but queued), or degraded
    extraction. None (auto-cleared) for clean likely_approved.
    """
    status = str(verdict.get("status") or "").upper()
    band = str(verdict.get("verdict") or "").lower()
    meta = verdict.get("metadata") or {}
    if meta.get("degraded_extractors"):
        return "pending_review"
    if status in ("REVIEW_REQUIRED", "NON_COMPLIANT", "LIKELY_REJECTED", "PENDING_ADVISORY"):
        return "pending_review"
    if band in ("borderline", "likely_rejected", "pending_advisory"):
        return "pending_review"
    # Only the deterministic engine may auto-clear; an advisory-only COMPLIANT
    # (fast mode / engine off) still needs a human pass.
    if meta.get("verdict_authority") == "advisory":
        return "pending_review"
    return None


class ReviewService:
    """Queue retrieval and decision recording."""

    def __init__(self) -> None:
        self._audit = AuditService()

    def queue(
        self,
        session: Session,
        *,
        tenant_id: uuid.UUID | str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Assets awaiting review, oldest first, with latest-verdict summary."""
        q = (
            session.query(AssetModel)
            .filter(AssetModel.review_state == "pending_review")
            .order_by(AssetModel.created_at.asc())
        )
        if tenant_id is not None:
            try:
                q = q.filter(AssetModel.tenant_id == uuid.UUID(str(tenant_id)))
            except ValueError:
                pass
        assets = q.offset(max(0, offset)).limit(max(1, min(limit, 200))).all()
        if not assets:
            return []

        asset_ids = [a.id for a in assets]
        verdicts = (
            session.query(VerdictModel)
            .filter(VerdictModel.asset_id.in_(asset_ids))
            .order_by(VerdictModel.created_at.asc())
            .all()
        )
        latest: dict[uuid.UUID, VerdictModel] = {}
        for v in verdicts:
            latest[v.asset_id] = v  # ascending order → last write wins

        items: list[dict[str, Any]] = []
        for a in assets:
            v = latest.get(a.id)
            result = dict(v.result) if v is not None and v.result else {}
            meta = result.get("metadata") or {}
            items.append(
                {
                    "asset_id": str(a.id),
                    "type": a.type,
                    "external_ref": a.external_ref,
                    "parent_asset_id": str(a.parent_asset_id) if a.parent_asset_id else None,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "has_media": bool(a.storage_uri),
                    "verdict": result.get("verdict"),
                    "compliance_status": result.get("status"),
                    "risk_score": result.get("risk_score"),
                    "rule_ids": sorted(
                        {
                            str(vi.get("rule_id"))
                            for vi in (result.get("violations") or [])
                            if isinstance(vi, dict) and vi.get("rule_id")
                        }
                    ),
                    "degraded_extractors": meta.get("degraded_extractors") or {},
                }
            )
        return items

    def submit_decision(
        self,
        session: Session,
        asset_id: uuid.UUID,
        *,
        reviewer: str,
        decision: str,
        reason: str | None = None,
        violation_feedback: list[dict[str, Any]] | None = None,
        source: str = "human_review",
        tenant_id: uuid.UUID | str | None = None,
    ) -> ReviewDecision:
        """
        Record a decision and transition the asset's review_state.

        Raises ValueError on bad input, LookupError if the asset is missing.
        """
        d = (decision or "").strip().lower()
        if d not in VALID_DECISIONS:
            raise ValueError(f"decision must be one of {VALID_DECISIONS}")
        s = (source or "human_review").strip().lower()
        if s not in VALID_SOURCES:
            raise ValueError(f"source must be one of {VALID_SOURCES}")
        if not (reviewer or "").strip():
            raise ValueError("reviewer is required")

        asset = session.query(AssetModel).filter(AssetModel.id == asset_id).first()
        if asset is None:
            raise LookupError("Asset not found")

        verdict = (
            session.query(VerdictModel)
            .filter(VerdictModel.asset_id == asset_id)
            .order_by(VerdictModel.created_at.desc())
            .first()
        )

        tid: uuid.UUID | None = None
        if tenant_id is not None:
            try:
                tid = uuid.UUID(str(tenant_id))
            except ValueError:
                tid = None

        record = ReviewDecision(
            asset_id=asset_id,
            verdict_id=verdict.id if verdict is not None else None,
            tenant_id=tid or asset.tenant_id,
            reviewer=reviewer.strip(),
            decision=d,
            reason=(reason or "").strip() or None,
            violation_feedback=_sanitize_feedback(violation_feedback),
            source=s,
        )
        session.add(record)

        before_state = {"review_state": asset.review_state}
        asset.review_state = _DECISION_TO_STATE[d]
        session.flush()

        self._audit.persist_audit_event(
            session,
            asset_id,
            verdict.id if verdict is not None else asset_id,
            "REVIEW_DECISION",
            tenant_id=asset.tenant_id,
            action="REVIEW_DECISION",
            actor={"reviewer": record.reviewer, "source": s},
            before_state=before_state,
            after_state={
                "review_state": asset.review_state,
                "decision": d,
                "false_positive_count": sum(
                    1
                    for f in (record.violation_feedback or [])
                    if f.get("assessment") == "false_positive"
                ),
            },
        )
        return record

    def decisions_for_asset(
        self, session: Session, asset_id: uuid.UUID
    ) -> list[dict[str, Any]]:
        rows = (
            session.query(ReviewDecision)
            .filter(ReviewDecision.asset_id == asset_id)
            .order_by(ReviewDecision.created_at.asc())
            .all()
        )
        return [decision_to_dict(r) for r in rows]


def decision_to_dict(r: ReviewDecision) -> dict[str, Any]:
    return {
        "id": str(r.id),
        "asset_id": str(r.asset_id),
        "verdict_id": str(r.verdict_id) if r.verdict_id else None,
        "reviewer": r.reviewer,
        "decision": r.decision,
        "reason": r.reason,
        "violation_feedback": r.violation_feedback or [],
        "source": r.source,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _sanitize_feedback(feedback: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in feedback or []:
        if not isinstance(f, dict):
            continue
        assessment = str(f.get("assessment") or "").strip().lower()
        if assessment not in ("true_positive", "false_positive"):
            continue
        out.append(
            {
                "violation_id": str(f.get("violation_id") or "") or None,
                "rule_id": str(f.get("rule_id") or "") or None,
                "assessment": assessment,
                "note": str(f.get("note") or "").strip()[:2000] or None,
            }
        )
    return out
