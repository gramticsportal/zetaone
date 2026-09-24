"""
Optional final LLM pass: deterministic signals + verdict + (optional) Gemini VLM summary → one text model call.

By default (ZATAONE_VERDICT_AUTHORITY=advisory) the LLM synthesis is the user-visible verdict on Full;
rule-engine outcomes remain in the audit graph.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

import zataone.integrations.gemini as gemini_mod
import zataone.integrations.ollama as ollama_mod
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

_SYSTEM_SECOND_READ = """You are the final compliance assessor (Full pipeline). Your inputs are a JSON object with:
- deterministic_verdict: rule-engine outcome (audit baseline; may include false positives).
- signals: extracted features (cite by id when relevant).
- violations: rule hits from the engine (explainability; may be wrong on edge cases).
- policy_context: policy pack summary plus clauses_for_review and rules_for_review.
- advisory_vlm: optional vision inspection (field 'inspection' is free text; may be imperfect).

Task: synthesize signals, VLM, violations, and policy_context into the user-visible outcome.
Weigh VLM + OCR/signals over weak vision-only rule hits when they conflict (e.g. academic slide vs 'campaign poster').
Output JSON: schema_version ("1.0"), summary,
recommended_compliance_status (COMPLIANT | REVIEW_REQUIRED | LIKELY_REJECTED),
recommended_verdict (likely_approved | borderline | likely_rejected),
agreement_with_deterministic (aligns | mostly_aligns | unclear | diverges),
rationale, cited_signal_ids (array, may be empty),
disclaimer noting rule-engine hits are audit evidence. No markdown fences."""

_SYSTEM_FAST_COMBINED = """Quick compliance: ONE pass over the image. Inspect visible copy/claims, compare to policy_context, output JSON only.
Keys: schema_version ("1.0"), inspection (brief factual vision notes, max ~400 words), summary,
agreement_with_deterministic (aligns|mostly_aligns|unclear|diverges),
recommended_compliance_status (COMPLIANT|REVIEW_REQUIRED|LIKELY_REJECTED),
recommended_verdict (likely_approved|borderline|likely_rejected),
rationale (cite clause_id or rule_id), cited_signal_ids ([]), disclaimer.
No markdown fences."""

_SYSTEM_FAST_VLM_POLICY = """You are the primary compliance assessor (Quick pipeline). The YAML rule engine did NOT run.
Compare advisory_vlm.inspection and any asset_content_preview to policy_context.clauses_for_review and rules_for_review.

Output JSON: schema_version ("1.0"), summary, agreement_with_deterministic (aligns | mostly_aligns | unclear | diverges),
recommended_compliance_status (COMPLIANT | REVIEW_REQUIRED | LIKELY_REJECTED),
recommended_verdict (likely_approved | borderline | likely_rejected),
rationale (cite clause_id or rule_id when referencing policy), cited_signal_ids (empty array),
disclaimer noting this is an LLM assessment against the policy corpus, not a rule-engine audit. No markdown fences."""

_SYSTEM_FULL_LLM_POLICY = """You are the primary compliance assessor (Full pipeline, rule engine off).
Use signals (if any), advisory_vlm.inspection, and policy_context to judge the asset against policy.

Output JSON: schema_version ("1.0"), summary, agreement_with_deterministic (aligns | mostly_aligns | unclear | diverges),
recommended_compliance_status (COMPLIANT | REVIEW_REQUIRED | LIKELY_REJECTED),
recommended_verdict (likely_approved | borderline | likely_rejected),
rationale, cited_signal_ids (only ids present in signals), disclaimer. No markdown fences."""


def _system_prompt_for_review_mode(review_mode: str) -> str:
    if review_mode == "fast_vlm_policy":
        return _SYSTEM_FAST_VLM_POLICY
    if review_mode == "full_signals_vlm_policy":
        return _SYSTEM_FULL_LLM_POLICY
    return _SYSTEM_SECOND_READ


def _resolve_review_mode(meta: dict[str, Any]) -> str:
    mode = str(meta.get("pipeline_mode") or "full").strip().lower()
    engine_ran = bool(meta.get("policy_engine_ran"))
    if mode == "fast":
        return "fast_vlm_policy"
    if not engine_ran:
        return "full_signals_vlm_policy"
    return "advisory_second_read"

_VLM_SYSTEM = """You extract structured evidence from an image for an ad-compliance system.
You do NOT decide compliance. Be factual; do not invent on-image text—use notes when illegible.
Return ONLY a single JSON object (no markdown fences, no prose outside JSON)."""

_VLM_PROMPT_FOCUS = (
    "Fill every field. ocr_text = all readable on-image text (headlines, body, CTAs, fine print). "
    "ad_claims_text = promotional claims, offers, guarantees, health/finance promises, CTAs "
    "(best input for rule matching; omit pure UI chrome). "
    "objects = notable objects/logos/people with optional bbox [x,y,w,h] in pixels if clear. "
    "scene_description = neutral visual summary for a later judge (not for regex matching). "
    "is_advertisement = whether this looks like an ad/promo creative. Observations only—no verdict."
)

_VLM_JSON_SCHEMA_HINT = """{
  "is_advertisement": true,
  "ocr_text": "string — all visible text, reading order",
  "ad_claims_text": "string — claims/offers/CTAs/disclaimers for policy matching",
  "objects": [{"label": "lowercase name", "confidence": 0.0, "bbox": [x, y, w, h]}],
  "scene_description": "string — neutral scene for LLM judge",
  "notes": "string — uncertainty / illegible regions"
}"""


def _vlm_max_output_tokens() -> int:
    v = (os.environ.get("GEMINI_VLM_MAX_TOKENS") or "").strip()
    if v.isdigit():
        return max(256, min(4096, int(v)))
    return 2048


def _fast_combined_max_tokens() -> int:
    v = (os.environ.get("ZATAONE_FAST_COMBINED_MAX_TOKENS") or "").strip()
    if v.isdigit():
        return max(512, min(2048, int(v)))
    return 1024


def _fast_review_max_tokens() -> int:
    v = (os.environ.get("ZATAONE_FAST_REVIEW_MAX_TOKENS") or "").strip()
    if v.isdigit():
        return max(512, min(4096, int(v)))
    return 1200


def _fast_model() -> str | None:
    m = (os.environ.get("GEMINI_FAST_MODEL") or os.environ.get("GEMINI_MODEL") or "").strip()
    return m or None


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
    Gemini vision pass → structured JSON packet.

    Returns (inspection_summary_for_llm, error, status) where status includes
    ``structured`` (normalized packet) and ``inspection`` (LLM-facing summary).
    """
    from zataone.document.vlm_packet import (
        inspection_summary_for_llm,
        normalize_vlm_structured,
        parse_vlm_json,
    )

    vlm_raw: str | None = None
    vlm_error: str | None = None
    structured: dict[str, Any] | None = None
    inspection: str | None = None
    try:
        vlm_user = _build_vlm_user_prompt(domain=domain, det=det)
        vlm_raw = gemini_mod.gemini_vision_image(
            image_bytes,
            vlm_user,
            system_prompt=_VLM_SYSTEM,
            model=os.environ.get("GEMINI_VLM_MODEL") or None,
            max_output_tokens=_vlm_max_output_tokens(),
            temperature=0.1,
        )
        parsed = parse_vlm_json(vlm_raw)
        if parsed is not None:
            structured = normalize_vlm_structured(parsed)
            inspection = inspection_summary_for_llm(structured) or None
        else:
            # Fallback: treat free text as scene/ocr blob for matcher+LLM
            fallback_text = (vlm_raw or "").strip()
            structured = normalize_vlm_structured(
                {
                    "ocr_text": fallback_text[:20000],
                    "ad_claims_text": "",
                    "objects": [],
                    "scene_description": fallback_text[:8000],
                    "notes": "vlm_json_parse_failed",
                }
            )
            inspection = fallback_text[:8000] or None
            vlm_error = "json_parse_failed"
    except Exception as e:
        vlm_error = str(e)[:800]
        logger.exception("Gemini vision summary failed")
        vlm_raw = None

    status: dict[str, Any] = {
        "vlm_eligible": True,
        "file_bytes_received": bool(image_bytes),
        "vlm_called": True,
        "vlm_succeeded": bool(inspection or structured),
        "vlm_error": vlm_error,
        "inspection": inspection,
        "structured": structured,
        "raw_response": (vlm_raw or "")[:12000] or None,
        "prompt_focus": _VLM_PROMPT_FOCUS,
        "skipped": False,
        "skipped_reason": None,
    }
    return inspection, vlm_error, status


def run_fast_combined_image_review(
    image_bytes: bytes,
    *,
    domain: str,
    verdict: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Quick path: single Gemini vision call with compact policy_context (replaces separate VLM + text LLM).
    """
    meta = verdict.get("metadata") or {}
    policy_ctx = build_policy_context_for_llm(
        meta,
        max_clauses=5,
        max_rule_snippets=4,
        max_clause_chars=400,
        max_rule_chars=200,
    )
    user_payload = {
        "domain": domain,
        "pipeline_mode": "fast",
        "policy_context": policy_ctx,
    }
    user_text = json.dumps(user_payload, ensure_ascii=True, default=str, separators=(",", ":"))
    raw = gemini_mod.gemini_vision_image(
        image_bytes,
        user_text,
        system_prompt=_SYSTEM_FAST_COMBINED,
        model=_fast_model(),
        max_output_tokens=_fast_combined_max_tokens(),
    )
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    data = json.loads(t)
    inspection = (data.pop("inspection", None) or "").strip() or None
    review = LlmFinalReviewV1.model_validate(data)
    stored = wrap_stored_review(review)
    vlm_status: dict[str, Any] = {
        "vlm_eligible": True,
        "file_bytes_received": bool(image_bytes),
        "vlm_called": True,
        "vlm_succeeded": bool(inspection),
        "vlm_error": None,
        "inspection": inspection,
        "skipped": False,
        "skipped_reason": None,
        "fast_combined": True,
    }
    return stored, vlm_status


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
        "structured": (vlm_status or {}).get("structured"),
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
    review_mode = _resolve_review_mode(meta)
    ctx_kwargs: dict[str, Any] = {"vlm_inspection": inspection}
    max_toks = _max_review_output_tokens()
    if review_mode == "fast_vlm_policy":
        ctx_kwargs.update(
            max_clauses=5,
            max_rule_snippets=4,
            max_clause_chars=400,
            max_rule_chars=200,
        )
        max_toks = _fast_review_max_tokens()
    elif review_mode == "full_signals_vlm_policy":
        ctx_kwargs.update(max_clauses=8, max_clause_chars=600)
        max_toks = _fast_review_max_tokens()
    policy_ctx = build_policy_context_for_llm(meta, **ctx_kwargs)
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
        review_mode=review_mode,
    )
    user_msg = context_json_for_prompt(ctx)
    model = _fast_model() if review_mode != "advisory_second_read" else (
        os.environ.get("GEMINI_REVIEW_MODEL") or None
    )
    review, execution = _advisory_json_from_provider(
        user_msg,
        system_prompt=_system_prompt_for_review_mode(review_mode),
        model=model,
        max_toks=max_toks,
        review_mode=review_mode,
    )
    stored = wrap_stored_review(review)
    stored.update(execution)
    return stored, vlm_status or {}


def _build_vlm_user_prompt(*, domain: str, det: dict[str, Any]) -> str:
    status = det.get("status", "")
    verdict = det.get("verdict", "")
    risk = det.get("risk_score", "")
    return f"""Pipeline context (for orientation only; you do not judge compliance):
- Compliance domain: {domain}
- Deterministic outcome (may be pending): status={status!r}, verdict={verdict!r}, risk_score={risk!r}

{_VLM_PROMPT_FOCUS}

Return ONLY this JSON shape (values filled from the image):
{_VLM_JSON_SCHEMA_HINT}"""


def _llm_enabled() -> bool:
    v = (os.environ.get("ZATAONE_LLM_FINAL_REVIEW") or "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    if v in ("1", "true", "yes", "on"):
        return True
    provider = _review_provider()
    if provider in {"ollama", "cascade"}:
        return True
    # Gemini default: on when its key is present.
    return bool(
        (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    )


def _review_provider() -> str:
    """Text-review backend. Gemini remains the compatibility default."""
    value = (os.environ.get("ZATAONE_REVIEW_PROVIDER") or "gemini").strip().lower()
    return value if value in {"gemini", "ollama", "cascade"} else "gemini"


def _ollama_review_model() -> str:
    return (
        os.environ.get("OLLAMA_REVIEW_MODEL")
        or os.environ.get("OLLAMA_LLM_MODEL")
        or "qwen3:8b"
    ).strip()


def _ollama_context_tokens() -> int:
    try:
        return max(4096, int(os.environ.get("OLLAMA_NUM_CTX") or "32768"))
    except ValueError:
        return 32768


def _gemini_key_present() -> bool:
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


def _advisory_json_from_ollama(
    user_msg: str,
    *,
    system_prompt: str,
    max_toks: int,
) -> tuple[LlmFinalReviewV1, dict[str, Any]]:
    """Run the same validated review contract on a self-hosted Ollama model."""
    model = _ollama_review_model()
    try:
        generated = ollama_mod.ollama_chat_detailed(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            model=model,
            response_format=LlmFinalReviewV1.model_json_schema(),
            options={
                "temperature": 0,
                "num_ctx": _ollama_context_tokens(),
                "num_predict": max_toks,
            },
            keep_alive=os.environ.get("OLLAMA_KEEP_ALIVE") or "15m",
            # Thinking is useful for hard tasks but expensive and can leak prose around
            # JSON. The structured compliance pass needs stable machine output.
            think=False,
        )
        review = _parse_json_lenient(generated.text)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise BadLlmReviewOutput(f"Ollama returned invalid review JSON: {exc}") from exc
    except Exception as exc:
        raise BadLlmReviewOutput(f"Ollama review request failed: {exc}") from exc

    metadata = {
        "review_provider": "ollama",
        "review_model": generated.model or model,
        "review_latency_ms": generated.latency_ms,
        "review_schema_valid": True,
        "review_fallback_reason": None,
        "review_inference": generated.metadata(),
    }
    return review, metadata


def _review_rejection_reason(
    review: LlmFinalReviewV1,
    *,
    review_mode: str,
    user_msg: str,
) -> str | None:
    """Objective cascade gates; never trust the model's numeric self-confidence."""
    if review.agreement_with_deterministic == "unclear":
        return "model_unclear"
    if review.agreement_with_deterministic == "diverges":
        return "model_diverges_from_deterministic"
    if review_mode in {"fast_vlm_policy", "full_signals_vlm_policy"}:
        if not review.recommended_compliance_status or not review.recommended_verdict:
            return "missing_primary_verdict"

    try:
        context = json.loads(user_msg)
    except json.JSONDecodeError:
        context = {}
    valid_signal_ids = {
        str(row.get("id"))
        for row in (context.get("signals") or [])
        if isinstance(row, dict) and row.get("id")
    }
    cited = {str(value) for value in review.cited_signal_ids if value}
    if cited - valid_signal_ids:
        return "invented_signal_citation"
    return None


def _advisory_json_from_provider(
    user_msg: str,
    *,
    system_prompt: str,
    model: str | None,
    max_toks: int,
    review_mode: str,
) -> tuple[LlmFinalReviewV1, dict[str, Any]]:
    """Run Gemini, Ollama, or local-first cascade under one output contract."""
    provider = _review_provider()
    if provider == "ollama":
        return _advisory_json_from_ollama(
            user_msg,
            system_prompt=system_prompt,
            max_toks=max_toks,
        )

    if provider == "cascade":
        local_review: LlmFinalReviewV1 | None = None
        reason: str | None = None
        local_meta: dict[str, Any] = {}
        try:
            local_review, local_meta = _advisory_json_from_ollama(
                user_msg,
                system_prompt=system_prompt,
                max_toks=max_toks,
            )
            reason = _review_rejection_reason(
                local_review,
                review_mode=review_mode,
                user_msg=user_msg,
            )
            if reason is None:
                local_meta["review_primary_provider"] = "ollama"
                return local_review, local_meta
        except BadLlmReviewOutput as exc:
            reason = f"local_failure:{str(exc)[:240]}"

        if not _gemini_key_present():
            if local_review is not None:
                local_meta["review_fallback_reason"] = reason
                local_meta["review_fallback_unavailable"] = True
                return local_review, local_meta
            raise BadLlmReviewOutput(
                f"Local review failed and Gemini fallback is unavailable: {reason}"
            )

        started = time.perf_counter()
        review = _advisory_json_from_gemini(
            user_msg,
            system_prompt=system_prompt,
            model=model,
            max_toks=max_toks,
        )
        return review, {
            "review_provider": "gemini",
            "review_model": model or os.environ.get("GEMINI_MODEL") or "gemini-default",
            "review_latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "review_schema_valid": True,
            "review_primary_provider": "ollama",
            "review_fallback_reason": reason,
            "review_local_attempt": local_meta or None,
        }

    if not _gemini_key_present():
        raise RuntimeError("Set GEMINI_API_KEY or GOOGLE_API_KEY")
    started = time.perf_counter()
    review = _advisory_json_from_gemini(
        user_msg,
        system_prompt=system_prompt,
        model=model,
        max_toks=max_toks,
    )
    return review, {
        "review_provider": "gemini",
        "review_model": model or os.environ.get("GEMINI_MODEL") or "gemini-default",
        "review_latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "review_schema_valid": True,
        "review_fallback_reason": None,
    }


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
        raise RuntimeError("LLM final review is disabled")

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
    review_mode = _resolve_review_mode(meta)
    inspection = advisory_vlm.get("inspection")
    policy_ctx = build_policy_context_for_llm(meta, vlm_inspection=inspection)

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
        review_mode=review_mode,
    )
    user_msg = context_json_for_prompt(ctx)
    max_toks = _max_review_output_tokens()
    m = os.environ.get("GEMINI_REVIEW_MODEL") or None
    try:
        review, execution = _advisory_json_from_provider(
            user_msg,
            system_prompt=_system_prompt_for_review_mode(review_mode),
            model=m,
            max_toks=max_toks,
            review_mode=review_mode,
        )
    except BadLlmReviewOutput:
        raise
    except Exception as e:
        # Rare: both JSON-mime and plain calls failed in _advisory_json_from_gemini's first try only if both raise
        raise BadLlmReviewOutput(f"Advisory model request failed: {e!s}") from e
    stored = wrap_stored_review(review)
    stored.update(execution)
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
