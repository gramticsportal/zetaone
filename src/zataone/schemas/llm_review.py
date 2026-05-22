"""
Structured input/output for the optional LLM final review (advisory only).

The deterministic policy verdict and persisted signals remain the explainability
and audit baseline; the LLM does not replace them.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class LlmFinalReviewV1(BaseModel):
    """Expected JSON from the review model (validate leniently)."""

    schema_version: str = "1.0"
    summary: str = Field(..., description="Short synthesis in plain language")
    agreement_with_deterministic: str = Field(
        ...,
        description="aligns | mostly_aligns | unclear | diverges",
    )
    rationale: str = Field(..., description="Why, citing rule/signal ideas in words")
    cited_signal_ids: list[str] = Field(default_factory=list)
    disclaimer: str = (
        "Advisory only. The binding compliance outcome is the deterministic verdict "
        "and the stored signals/evidence graph."
    )

    @field_validator("agreement_with_deterministic", mode="before")
    @classmethod
    def _normalize_agreement(cls, v: Any) -> str:
        if v is None:
            return "unclear"
        s = str(v).strip().lower().replace(" ", "_")
        allowed = {"aligns", "mostly_aligns", "unclear", "diverges"}
        if s in allowed:
            return s
        return "unclear"


def build_review_context(
    *,
    schema_version: str,
    asset_id: UUID,
    domain: str,
    asset_type: str,
    deterministic_verdict: dict[str, Any],
    signals: list[dict[str, Any]],
    violations: list[dict[str, Any]],
    advisory_vlm: dict[str, Any] | None,
    policy_context: dict[str, Any] | None = None,
    asset_content_preview: str | None = None,
) -> dict[str, Any]:
    """
    Single JSON object passed to the advisory text LLM.

    ``advisory_vlm`` is the optional first-pass vision inspection (VLM) output and metadata, merged
    into this object. ``vlm_image_summary`` duplicates ``advisory_vlm['inspection']`` for older prompts.
    """
    av = advisory_vlm or {
        "inspection": None,
        "prompt_focus": None,
        "skipped": True,
        "skipped_reason": "no_vision_input",
    }
    inspection = av.get("inspection")
    out: dict[str, Any] = {
        "schema_version": schema_version,
        "asset_id": str(asset_id),
        "domain": domain,
        "asset_type": asset_type,
        "deterministic_verdict": deterministic_verdict,
        "signals": signals,
        "violations": violations,
        "advisory_vlm": av,
        "vlm_image_summary": inspection,
        "_instructions": (
            "You receive only structured inputs. Do not invent OCR or object labels not present in signals. "
            "advisory_vlm.inspection is a first-pass VLM write-up: it may miss text or be wrong; treat persisted "
            "signals as the primary structured extractors. Use the vision inspection to reason about layout, "
            "salience, and anything not fully captured in signals when helpful. "
            "policy_context.clauses_for_review and rules_for_review are authoritative policy text for this run—"
            "cite rule_id or clause_id when your rationale references policy."
        ),
    }
    if policy_context:
        out["policy_context"] = policy_context
    if asset_content_preview:
        out["asset_content_preview"] = asset_content_preview[:4000]
    return out


def context_json_for_prompt(ctx: dict[str, Any]) -> str:
    """Compact JSON string for the user message body."""
    return json.dumps(ctx, ensure_ascii=True, default=str, separators=(",", ":"))


def wrap_stored_review(review: LlmFinalReviewV1) -> dict[str, Any]:
    out = review.model_dump()
    out["generated_at"] = datetime.now(timezone.utc).isoformat()
    return out
