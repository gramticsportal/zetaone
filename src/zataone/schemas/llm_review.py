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
    recommended_compliance_status: str | None = Field(
        default=None,
        description="COMPLIANT | REVIEW_REQUIRED | LIKELY_REJECTED when LLM is primary assessor",
    )
    recommended_verdict: str | None = Field(
        default=None,
        description="likely_approved | borderline | likely_rejected when LLM is primary assessor",
    )
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
    review_mode: str = "advisory_second_read",
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
    if review_mode == "fast_vlm_policy":
        instructions = (
            "Quick pipeline: the YAML rule engine did NOT run. Compare advisory_vlm.inspection and any "
            "asset_content_preview to policy_context.clauses_for_review and rules_for_review. "
            "Your recommended_compliance_status and recommended_verdict drive the user-visible outcome. "
            "Set agreement_with_deterministic to diverges when policy likely violated, aligns when clearly compliant. "
            "Cite clause_id or rule_id in rationale."
        )
    elif review_mode == "full_signals_vlm_policy":
        instructions = (
            "Full pipeline with rule engine OFF. Use signals (if any), advisory_vlm.inspection, and "
            "policy_context to assess compliance. recommended_* fields drive the displayed outcome. "
            "Do not invent signal ids; cite only ids present in signals."
        )
    else:
        instructions = (
            "Second read after the rule engine. Do not replace the deterministic verdict; use "
            "agreement_with_deterministic. Signals are primary structured extractors; VLM inspection "
            "supplements. policy_context.clauses_for_review and rules_for_review are authoritative policy text."
        )

    out: dict[str, Any] = {
        "schema_version": schema_version,
        "asset_id": str(asset_id),
        "domain": domain,
        "asset_type": asset_type,
        "review_mode": review_mode,
        "deterministic_verdict": deterministic_verdict,
        "signals": signals,
        "violations": violations,
        "advisory_vlm": av,
        "vlm_image_summary": inspection,
        "_instructions": instructions,
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
