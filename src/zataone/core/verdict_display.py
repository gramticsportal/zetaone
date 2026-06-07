# zataone — display vs deterministic compliance outcomes

from __future__ import annotations

from typing import Any


def _display_from_advisory(review: dict[str, Any]) -> tuple[str, str, str | None, bool]:
    """Map advisory JSON to display status / platform verdict."""
    if not review:
        return "REVIEW_REQUIRED", "borderline", "advisory_unavailable", True

    rec_status = str(review.get("recommended_compliance_status") or "").strip().upper()
    rec_verdict = str(review.get("recommended_verdict") or "").strip().lower()

    status_map: dict[str, tuple[str, str]] = {
        "COMPLIANT": ("COMPLIANT", "likely_approved"),
        "REVIEW_REQUIRED": ("REVIEW_REQUIRED", "borderline"),
        "LIKELY_REJECTED": ("LIKELY_REJECTED", "likely_rejected"),
        "REJECTED": ("LIKELY_REJECTED", "likely_rejected"),
    }
    if rec_status in status_map:
        display_status, display_platform = status_map[rec_status]
        if rec_verdict in ("likely_approved", "borderline", "likely_rejected"):
            display_platform = rec_verdict
        return display_status, display_platform, "advisory_policy_assessment", False

    agreement = str(review.get("agreement_with_deterministic") or "unclear").strip().lower()
    if agreement == "diverges":
        return "REVIEW_REQUIRED", "borderline", "advisory_policy_divergence", True
    if agreement == "aligns":
        return "COMPLIANT", "likely_approved", "advisory_policy_aligned", False
    return "REVIEW_REQUIRED", "borderline", "advisory_unclear", True


def apply_display_verdict(
    verdict: dict[str, Any],
    *,
    signal_count: int,
    pipeline_mode: str = "full",
    policy_engine_ran: bool | None = None,
) -> dict[str, Any]:
    """
    Set display fields on verdict dict. Top-level status/verdict reflect what UI should show.
    When the rule engine did not run (Quick or ZATAONE_POLICY_ENGINE_ENABLED=false),
    the advisory LLM assessment is the display authority.
    """
    meta = dict(verdict.get("metadata") or {})
    mode = (pipeline_mode or meta.get("pipeline_mode") or "full").strip().lower()
    engine_ran = (
        policy_engine_ran
        if policy_engine_ran is not None
        else bool(meta.get("policy_engine_ran"))
    )
    advisory_primary = mode == "fast" or not engine_ran

    det_status = str(verdict.get("status") or "UNKNOWN")
    det_platform = str(verdict.get("verdict") or "unknown")
    meta["deterministic_compliance_status"] = det_status
    meta["deterministic_verdict"] = det_platform
    meta["signal_count"] = signal_count
    meta["pipeline_mode"] = mode
    meta["policy_engine_ran"] = engine_ran
    meta["policy_engine_enabled"] = engine_ran
    meta["verdict_authority"] = "advisory" if advisory_primary else "deterministic"

    review = verdict.get("llm_final_review") or {}

    if advisory_primary:
        display_status, display_platform, override_reason, elevated = _display_from_advisory(review)
        verdict_source = "advisory"
    else:
        # Engine ran: deterministic is audit authority; LLM may escalate for human review.
        agreement = str(review.get("agreement_with_deterministic") or "unclear").strip().lower()
        elevated = False
        override_reason: str | None = None
        display_status = det_status
        display_platform = det_platform
        verdict_source = "deterministic"

        if signal_count == 0:
            elevated = True
            display_status = "REVIEW_REQUIRED"
            display_platform = "borderline"
            override_reason = "no_extractor_signals"
            verdict_source = "advisory_escalation"
        elif agreement == "diverges":
            elevated = True
            display_status = "REVIEW_REQUIRED"
            display_platform = "borderline"
            override_reason = "advisory_diverges_from_deterministic"
            verdict_source = "advisory_escalation"

    meta["elevated_by_advisory"] = elevated
    meta["verdict_source"] = verdict_source
    meta["override_reason"] = override_reason
    meta["display_compliance_status"] = display_status
    meta["display_verdict"] = display_platform

    verdict["metadata"] = meta
    verdict["status"] = display_status
    verdict["verdict"] = display_platform
    return verdict


def enrich_api_verdict_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Add explicit display/deterministic fields for API consumers."""
    meta = result.get("metadata") or {}
    out = dict(result)
    out["deterministic_compliance_status"] = meta.get(
        "deterministic_compliance_status", result.get("status", "")
    )
    out["deterministic_verdict"] = meta.get("deterministic_verdict", result.get("verdict", ""))
    out["display_compliance_status"] = result.get("status", "")
    out["display_verdict"] = result.get("verdict", "")
    out["elevated_by_advisory"] = bool(meta.get("elevated_by_advisory"))
    out["verdict_source"] = meta.get("verdict_source", "deterministic")
    out["verdict_authority"] = meta.get("verdict_authority", out["verdict_source"])
    out["override_reason"] = meta.get("override_reason")
    out["pipeline_mode"] = meta.get("pipeline_mode", "full")
    out["policy_engine_ran"] = meta.get("policy_engine_ran", False)
    out["signal_count"] = meta.get("signal_count")
    return out
