# zataone — display vs deterministic compliance outcomes

from __future__ import annotations

from typing import Any


def apply_display_verdict(verdict: dict[str, Any], *, signal_count: int) -> dict[str, Any]:
    """
    Set display fields on verdict dict. Top-level status/verdict reflect what UI should show.
    Deterministic outcomes are preserved in metadata for audit.
    """
    det_status = str(verdict.get("status") or "UNKNOWN")
    det_platform = str(verdict.get("verdict") or "unknown")
    meta = dict(verdict.get("metadata") or {})

    meta["deterministic_compliance_status"] = det_status
    meta["deterministic_verdict"] = det_platform
    meta["signal_count"] = signal_count

    review = verdict.get("llm_final_review") or {}
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
    det = meta.get("deterministic_compliance_status") or result.get("status", "")
    out["deterministic_compliance_status"] = det
    out["deterministic_verdict"] = meta.get("deterministic_verdict", result.get("verdict", ""))
    out["display_compliance_status"] = result.get("status", "")
    out["display_verdict"] = result.get("verdict", "")
    out["elevated_by_advisory"] = bool(meta.get("elevated_by_advisory"))
    out["verdict_source"] = meta.get("verdict_source", "deterministic")
    out["override_reason"] = meta.get("override_reason")
    out["pipeline_mode"] = meta.get("pipeline_mode", "full")
    out["signal_count"] = meta.get("signal_count")
    return out
