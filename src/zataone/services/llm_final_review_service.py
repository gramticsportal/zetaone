"""
Optional final LLM pass: deterministic signals + verdict + (optional) Gemini VLM summary → one text model call.

Does not change policy logic; result is stored under verdict.result['llm_final_review'].
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

import zataone.integrations.gemini as gemini_mod
from zataone.models import (
    Asset as AssetModel,
    Signal as SignalModel,
    Verdict as VerdictModel,
    Violation as ViolationModel,
)
from pydantic import ValidationError

from zataone.core.policy_context import build_policy_context_for_llm
from zataone.schemas.llm_review import (
    LlmFinalReviewV1,
    build_review_context,
    context_json_for_prompt,
    wrap_stored_review,
)

logger = logging.getLogger(__name__)


class BadLlmReviewOutput(Exception):
    """The model did not return valid / parseable review JSON."""


class AssetNotReadyForLlmReview(Exception):
    """Pipeline not complete or missing rows."""

_CTX_VERSION = "1.0"

_SYSTEM = """You are a compliance review assistant. Your inputs are a JSON object with:
- deterministic_verdict: the policy engine outcome already computed (authoritative for product logic).
- signals: extracted features (explainability; cite these by id when relevant).
- violations: rule hits linked to the assessment.
- policy_context: policy pack summary plus clauses_for_review and rules_for_review (use these for policy reasoning).
- advisory_vlm: optional first-pass vision inspection (field 'inspection' is free text from a VLM; may be imperfect).
- vlm_image_summary: duplicate of advisory_vlm.inspection when present (legacy alias).
- asset_content_preview: optional raw text when extractors were skipped (fast mode).

Task: provide an advisory second read grounded in policy_context when present. Do NOT replace the deterministic verdict.
Output a single JSON object with keys: schema_version ("1.0"), summary, agreement_with_deterministic
(one of: aligns, mostly_aligns, unclear, diverges), rationale, cited_signal_ids (array of signal id strings, may be empty),
disclaimer (include the standard advisory text from the schema). No markdown fences. No other top-level keys."""

_VLM_SYSTEM = """You support an advisory compliance workflow. You do not set or override policy.
Describe what is visible in the image in ways that help a separate text model reason about the asset.
Be factual; do not invent on-image text—say when text is illegible or uncertain."""

_VLM_PROMPT_FOCUS = (
    "Read the image for compliance-relevant cues: visible copy/headlines/disclaimers/fine print and their "
    "placement; brands and endorsements; imagery (people, demographics, before/after, urgency); salience "
    "(what draws the eye vs buried); contrast/readability; possible tension with a strict legal reading. "
    "Observations only—no final verdict."
)


def _vlm_max_output_tokens() -> int:
    v = (os.environ.get("GEMINI_VLM_MAX_TOKENS") or "").strip()
    if v.isdigit():
        return max(256, min(4096, int(v)))
    return 1200


def _signal_rows_from_raw(signals: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for s in signals or []:
        if isinstance(s, dict):
            rows.append(
                {
                    "id": str(s.get("id") or s.get("signal_id") or ""),
                    "extractor_id": s.get("extractor_id", ""),
                    "signal_type": s.get("signal_type", ""),
                    "confidence": s.get("confidence"),
                    "value": s.get("value") or s.get("raw_data") or {},
                }
            )
            continue
        rows.append(
            {
                "id": str(getattr(s, "id", "") or ""),
                "extractor_id": getattr(s, "extractor_id", ""),
                "signal_type": getattr(s, "signal_type", ""),
                "confidence": getattr(s, "confidence", None),
                "value": getattr(s, "value", None) or getattr(s, "raw_data", None) or {},
            }
        )
    return rows


def _violation_rows_from_raw(violations: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for v in violations or []:
        if isinstance(v, dict):
            rows.append(
                {
                    "id": str(v.get("id") or ""),
                    "rule_id": v.get("rule_id", ""),
                    "violation_type": v.get("violation_type", ""),
                    "signal_id": str(v.get("signal_id") or ""),
                }
            )
            continue
        rows.append(
            {
                "id": str(getattr(v, "id", "") or ""),
                "rule_id": getattr(v, "rule_id", ""),
                "violation_type": getattr(v, "violation_type", ""),
                "signal_id": str(getattr(v, "signal_id", "") or ""),
            }
        )
    return rows


def run_gemini_vlm_inspection(
    image_bytes: bytes,
    *,
    domain: str,
    det: dict[str, Any],
) -> tuple[str | None, str | None, dict[str, Any]]:
    """
    Gemini vision pass only. Safe to run in parallel with deterministic extraction.
    """
    vlm_summary: str | None = None
    vlm_error: str | None = None
    try:
        vlm_user = _build_vlm_user_prompt(domain=domain, det=det)
        vlm_summary = gemini_mod.gemini_vision_image(
            image_bytes,
            vlm_user,
            system_prompt=_VLM_SYSTEM,
            model=os.environ.get("GEMINI_VLM_MODEL") or None,
            max_output_tokens=_vlm_max_output_tokens(),
        )
    except Exception as e:
        vlm_error = str(e)[:800]
        logger.exception("Gemini vision summary failed")
        vlm_summary = None

    status: dict[str, Any] = {
        "vlm_eligible": True,
        "file_bytes_received": bool(image_bytes),
        "vlm_called": True,
        "vlm_succeeded": bool((vlm_summary or "").strip()),
        "vlm_error": vlm_error,
        "inspection": (vlm_summary or "").strip() or None,
        "skipped": False,
        "skipped_reason": None,
    }
    return vlm_summary, vlm_error, status


def run_advisory_synthesis_in_memory(
    *,
    domain: str,
    asset: Any,
    asset_id: str | None,
    verdict: dict[str, Any],
    signals: list[Any],
    violations: list[Any],
    vlm_status: dict[str, Any] | None,
    image_bytes: bytes | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Advisory JSON from in-memory pipeline state (no DB reads)."""
    if not _llm_enabled():
        raise RuntimeError("LLM final review is disabled")
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY")

    asset_type = getattr(asset, "type", None) or "text"
    det = {
        "verdict": verdict.get("verdict", ""),
        "status": verdict.get("status", ""),
        "risk_score": verdict.get("risk_score"),
    }

    if vlm_status is None:
        if asset_type == "image" and image_bytes:
            _, _, vlm_status = run_gemini_vlm_inspection(image_bytes, domain=domain, det=det)
        else:
            vlm_status = {
                "vlm_eligible": False,
                "skipped": True,
                "skipped_reason": "not_image",
                "inspection": None,
            }

    inspection = (vlm_status or {}).get("inspection")
    advisory_vlm = {
        "inspection": inspection,
        "prompt_focus": _VLM_PROMPT_FOCUS,
        "skipped": bool((vlm_status or {}).get("skipped")),
        "skipped_reason": (vlm_status or {}).get("skipped_reason"),
    }

    aid: UUID | None = None
    if asset_id:
        try:
            aid = UUID(str(asset_id))
        except ValueError:
            aid = None

    meta = verdict.get("metadata") or {}
    policy_ctx = build_policy_context_for_llm(meta)
    content_preview = None
    raw_content = getattr(asset, "content", None)
    if raw_content and asset_type == "text":
        content_preview = str(raw_content)

    ctx = build_review_context(
        schema_version=_CTX_VERSION,
        asset_id=aid or UUID(int=0),
        domain=domain,
        asset_type=asset_type,
        deterministic_verdict=det,
        signals=_signal_rows_from_raw(signals),
        violations=_violation_rows_from_raw(violations),
        advisory_vlm=advisory_vlm,
        policy_context=policy_ctx,
        asset_content_preview=content_preview,
    )
    user_msg = context_json_for_prompt(ctx)
    review = _advisory_json_from_gemini(
        user_msg,
        system_prompt=_SYSTEM,
        model=os.environ.get("GEMINI_REVIEW_MODEL") or None,
        max_toks=_max_review_output_tokens(),
    )
    stored = wrap_stored_review(review)
    return stored, vlm_status or {}


def _build_vlm_user_prompt(*, domain: str, det: dict[str, Any]) -> str:
    status = det.get("status", "")
    verdict = det.get("verdict", "")
    risk = det.get("risk_score", "")
    return f"""Pipeline context (authoritative for logic; you assist interpretation only):
- Compliance domain: {domain}
- Deterministic outcome: status={status!r}, verdict={verdict!r}, risk_score={risk!r}

{_VLM_PROMPT_FOCUS}

Respond in clear sections or bullet points (plain text, not JSON). If the image is not an ad or is blank, say so briefly."""


def _llm_enabled() -> bool:
    v = (os.environ.get("ZATAONE_LLM_FINAL_REVIEW") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    # default: on when Gemini key is present
    return bool(
        (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    )


def _signal_row(s: SignalModel) -> dict[str, Any]:
    return {
        "id": str(s.id),
        "extractor_id": s.extractor_id,
        "signal_type": s.signal_type,
        "confidence": s.confidence,
        "value": s.value,
    }


def _violation_row(v: ViolationModel) -> dict[str, Any]:
    return {
        "id": str(v.id),
        "rule_id": v.rule_id,
        "violation_type": v.violation_type,
        "signal_id": str(v.signal_id),
    }


def _parse_json_lenient(raw: str) -> LlmFinalReviewV1:
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    data = json.loads(t)
    return LlmFinalReviewV1.model_validate(data)


def _max_review_output_tokens() -> int:
    v = (os.environ.get("GEMINI_REVIEW_MAX_TOKENS") or "").strip()
    if v.isdigit():
        return max(512, min(8192, int(v)))
    return 4096


def _advisory_json_from_gemini(
    user_msg: str, *, system_prompt: str, model: str | None, max_toks: int
) -> LlmFinalReviewV1:
    """One advisory text call, then one repair call if the model output is not valid JSON."""
    try:
        raw = gemini_mod.gemini_text_chat(
            user_msg,
            system_prompt=system_prompt,
            model=model,
            max_output_tokens=max_toks,
            temperature=0.2,
            response_mime_type="application/json",
        )
    except Exception:
        logger.info("JSON responseMimeType not accepted or call failed; retrying without it")
        raw = gemini_mod.gemini_text_chat(
            user_msg,
            system_prompt=system_prompt,
            model=model,
            max_output_tokens=max_toks,
            temperature=0.2,
        )

    first_parse_err: Exception | None = None
    try:
        return _parse_json_lenient(raw)
    except (json.JSONDecodeError, ValidationError) as e0:
        first_parse_err = e0
        logger.warning("Advisory review JSON parse failed: %s", e0)

    fix_prompt = (
        "The text below was supposed to be ONE valid JSON object but it is invalid or truncated (e.g. unterminated string). "
        "Output ONLY a single valid JSON object with keys: "
        "schema_version, summary, agreement_with_deterministic, rationale, cited_signal_ids, disclaimer. "
        "agreement_with_deterministic must be one of: aligns, mostly_aligns, unclear, diverges. "
        "Use short summary and rationale if needed. No markdown fences, no other text.\n\n"
        f"Bad output:\n{raw[:8000]}"
    )
    try:
        raw2 = gemini_mod.gemini_text_chat(
            fix_prompt,
            system_prompt="You only output one valid JSON object.",
            model=model,
            max_output_tokens=max_toks,
            temperature=0.0,
            response_mime_type="application/json",
        )
    except Exception:
        raw2 = gemini_mod.gemini_text_chat(
            fix_prompt,
            system_prompt="You only output one valid JSON object.",
            model=model,
            max_output_tokens=max_toks,
            temperature=0.0,
        )
    try:
        return _parse_json_lenient(raw2)
    except (json.JSONDecodeError, ValidationError) as e2:
        first = f"{first_parse_err!s}" if first_parse_err else "unknown"
        raise BadLlmReviewOutput(
            f"Advisory model returned unparseable JSON: {e2!s}. (First parse: {first})"
        ) from e2


def run_llm_final_review(
    session: Session,
    asset_id: UUID,
    *,
    domain: str,
    image_bytes: bytes | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Load graph from DB, optional Gemini VLM on image, one Gemini text call for advisory JSON, merge into verdict.

    Returns (stored_review_dict, vlm_status_dict) — vlm_status is for clients/logs (not persisted in verdict).
    """
    if not _llm_enabled():
        raise RuntimeError("LLM final review is disabled (ZATAONE_LLM_FINAL_REVIEW=0 or no GEMINI_API_KEY)")

    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY")

    asset = session.query(AssetModel).filter(AssetModel.id == asset_id).first()
    if asset is None:
        raise AssetNotReadyForLlmReview("Asset not found")

    verdict = (
        session.query(VerdictModel)
        .filter(VerdictModel.asset_id == asset_id)
        .order_by(VerdictModel.created_at.desc())
        .first()
    )
    if verdict is None or asset.status != "completed":
        raise AssetNotReadyForLlmReview(
            "No completed verdict for this asset; run the compliance pipeline first"
        )

    signals = session.query(SignalModel).filter(SignalModel.asset_id == asset_id).all()
    violations = session.query(ViolationModel).filter(ViolationModel.asset_id == asset_id).all()

    det = {
        "verdict": (verdict.result or {}).get("verdict", ""),
        "status": (verdict.result or {}).get("status", verdict.status or ""),
        "risk_score": (verdict.result or {}).get("risk_score", verdict.risk_score),
    }

    vlm_summary: str | None = None
    vlm_error: str | None = None
    vlm_eligible = bool(image_bytes) and (asset.type == "image")
    if vlm_eligible:
        vlm_summary, vlm_error, _st = run_gemini_vlm_inspection(
            image_bytes, domain=domain, det=det
        )
        advisory_vlm = {
            "inspection": vlm_summary,
            "prompt_focus": _VLM_PROMPT_FOCUS,
            "skipped": False,
            "skipped_reason": None,
        }
    else:
        reason = "asset_not_image" if (asset.type != "image") else "no_image_bytes_in_request"
        vlm_summary = None
        vlm_error = None
        advisory_vlm = {
            "inspection": None,
            "prompt_focus": _VLM_PROMPT_FOCUS,
            "skipped": True,
            "skipped_reason": reason,
        }

    meta = (verdict.result or {}).get("metadata") or {}
    policy_ctx = build_policy_context_for_llm(meta)

    ctx = build_review_context(
        schema_version=_CTX_VERSION,
        asset_id=asset_id,
        domain=domain,
        asset_type=asset.type,
        deterministic_verdict=det,
        signals=[_signal_row(s) for s in signals],
        violations=[_violation_row(v) for v in violations],
        advisory_vlm=advisory_vlm,
        policy_context=policy_ctx,
    )
    user_msg = context_json_for_prompt(ctx)
    max_toks = _max_review_output_tokens()
    m = os.environ.get("GEMINI_REVIEW_MODEL") or None
    try:
        review = _advisory_json_from_gemini(
            user_msg, system_prompt=_SYSTEM, model=m, max_toks=max_toks
        )
    except BadLlmReviewOutput:
        raise
    except Exception as e:
        # Rare: both JSON-mime and plain calls failed in _advisory_json_from_gemini's first try only if both raise
        raise BadLlmReviewOutput(f"Advisory model request failed: {e!s}") from e
    stored = wrap_stored_review(review)
    vlm_status: dict[str, Any] = {
        "vlm_eligible": vlm_eligible,
        "file_bytes_received": bool(image_bytes and len(image_bytes) > 0),
        "vlm_called": vlm_eligible,
        "vlm_succeeded": bool((vlm_summary or "").strip()),
        "vlm_error": vlm_error,
        "inspection": (vlm_summary or "").strip() or None,
        "skipped": not vlm_eligible,
        "skipped_reason": None if vlm_eligible else advisory_vlm.get("skipped_reason"),
    }
    return stored, vlm_status


def merge_verdict_with_llm_review(
    session: Session,
    asset_id: UUID,
    stored: dict[str, Any],
) -> None:
    """Mutate latest verdict JSON; caller should session.commit()."""
    verdict = (
        session.query(VerdictModel)
        .filter(VerdictModel.asset_id == asset_id)
        .order_by(VerdictModel.created_at.desc())
        .first()
    )
    if verdict is None:
        raise AssetNotReadyForLlmReview("Verdict not found")
    base: dict[str, Any] = dict(verdict.result) if isinstance(verdict.result, dict) else {}
    base["llm_final_review"] = stored
    verdict.result = base
    session.add(verdict)
