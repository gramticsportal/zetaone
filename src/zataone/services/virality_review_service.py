"""Virality Index — LLM advisory pass + offline heuristic.

Runs concurrently with the compliance path (see ``core/pipeline_run.start_virality_review``),
so it needs no compliance input to produce scores. Compliance conflicts are attached
afterwards from the actual violations rather than guessed by the model.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

import zataone.integrations.gemini as gemini_mod
from zataone.core.extractor_flags import virality_review_enabled
from zataone.models import Asset as AssetModel, Verdict as VerdictModel
from zataone.schemas.virality_review import (
    ViralityDiagnostics,
    ViralityDimensions,
    ViralityReviewV2,
    wrap_stored_virality,
)
from zataone.virality.library import load_viral_patterns, patterns_for_prompt

logger = logging.getLogger(__name__)

__all__ = [
    "AssetNotReadyForViralityReview",
    "BadViralityOutput",
    "annotate_compliance_conflicts",
    "merge_verdict_with_virality",
    "run_virality_in_memory",
    "run_virality_review",
    "score_virality_offline",
    "virality_review_enabled",
]

# Absolute / high-arousal wording that lifts attention but tends to cost compliance.
_RISKY_AMPLIFIERS = ("guaranteed", "cure", "100%", "miracle", "risk-free", "never fails")


class BadViralityOutput(Exception):
    """Model returned invalid JSON."""


class AssetNotReadyForViralityReview(Exception):
    """Missing asset or no scoreable text."""


_SYSTEM = """You score ad copy for sharing potential (Virality Index).
Compliance is judged by a separate deterministic engine — do not attempt a compliance verdict.

Score these seven dimensions 0-100. They come from the sharing research; use them as defined,
not as loose synonyms:
- arousal: high-ACTIVATION emotion of ANY valence (awe, anger, anxiety, amusement). Calm
  positivity such as contentment scores LOW even when the copy is pleasant.
- social_currency: does passing this on make the sharer look smart, in-the-know, or on-brand
  for who they want to be seen as.
- practical_value: useful enough that sharing it actively helps someone.
- story: a narrative or dramatic arc carries the message, rather than a flat assertion.
- novelty: surprising; violates an expectation the reader already holds.
- triggers: tied to a frequent cue in the environment (a time of day, season, routine, place)
  that would repeatedly bring the ad back to mind.
- public_observability: the product or behaviour is visible to others and easy to imitate.

Also report two DIAGNOSTICS. These are NOT part of the score:
- clarity: how easily a first-time reader gets the point.
- brand_prominence: how heavily the brand/logo/name dominates. High values are a negative
  signal for sharing, so report it honestly rather than rewarding it.

Compare the ad to the viral pattern library. If a pattern is close, name it and suggest how to
raise the weak dimensions WITHOUT adding prohibited claims (no fake guarantees, disease cures).

Output JSON only:
dimensions: { arousal, social_currency, practical_value, story, novelty, triggers,
  public_observability } each 0-100,
diagnostics: { clarity, brand_prominence } each 0-100,
closest_pattern_id (an id from the library, or null),
closest_pattern_name,
pattern_match_strength (strong|moderate|weak|none),
suggestions (array of 3 short actionable strings, each naming the dimension it lifts),
summary (one sentence),
compliance_conflicts (array of strings naming wording in THIS copy that trades compliance for
attention; empty array if none).
Do not include virality_index — it is computed from dimensions. No markdown fences."""


def _repair_json(t: str) -> str:
    """
    Salvage the near-JSON models sometimes emit: prose wrapped around the object,
    ``//`` comments, and trailing commas. The lookbehind keeps ``https://`` intact.
    """
    start, end = t.find("{"), t.rfind("}")
    if start != -1 and end > start:
        t = t[start : end + 1]
    t = re.sub(r"(?<!:)//[^\n\r]*", "", t)
    t = re.sub(r",(\s*[}\]])", r"\1", t)
    return t


def _parse_json(raw: str) -> ViralityReviewV2:
    t = raw.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        data = json.loads(t)
    except json.JSONDecodeError as e:
        try:
            data = json.loads(_repair_json(t))
        except json.JSONDecodeError:
            # Log the payload; silent heuristic fallback otherwise hides prompt drift.
            logger.warning("Virality model returned unparseable JSON: %s", t[:600])
            raise BadViralityOutput(f"Virality model did not return JSON: {e}") from e
    return ViralityReviewV2.model_validate(data)


def _violation_labels(violations: list[Any] | None) -> list[str]:
    out: list[str] = []
    for v in violations or []:
        if isinstance(v, dict):
            ev = v.get("evidence_data") or {}
            out.append(str(ev.get("matched_text") or ev.get("matched_term") or v.get("rule_id") or "violation"))
        else:
            out.append(str(getattr(v, "rule_id", None) or v))
    return out[:8]


def annotate_compliance_conflicts(
    stored: dict[str, Any],
    *,
    violations: list[Any] | None = None,
    compliance_status: str | None = None,
) -> dict[str, Any]:
    """Merge engine-derived conflict notes into a scored result. Idempotent."""
    hits = _violation_labels(violations)
    notes: list[str] = list(stored.get("compliance_conflicts") or [])
    if hits:
        note = (
            "Compliance engine flagged: "
            + ", ".join(hits)
            + " — keep these fixes; raise virality through framing, not stronger claims."
        )
        if note not in notes:
            notes.append(note)
    if compliance_status:
        stored["compliance_status_at_scoring"] = compliance_status
    stored["compliance_conflicts"] = notes
    return stored


def score_virality_offline(text: str, *, compliance_hits: list[str] | None = None) -> dict[str, Any]:
    """Deterministic fallback when Gemini is off (landing demo, tests, LLM failure)."""
    t = (text or "").strip().lower()
    if not t:
        review = ViralityReviewV2(
            dimensions=ViralityDimensions(
                arousal=5,
                social_currency=5,
                practical_value=5,
                story=5,
                novelty=10,
                triggers=5,
                public_observability=5,
            ),
            diagnostics=ViralityDiagnostics(clarity=20, brand_prominence=0),
            summary="No copy to score.",
            suggestions=["Add a concrete hook in the first line."],
        )
        return wrap_stored_virality(review)

    def has(*words: str) -> bool:
        return any(w in t for w in words)

    word_count = len(t.split())
    # High activation of either valence — anger/anxiety count as much as excitement.
    arousal = (
        30
        + (20 if has("!", "now", "today", "instant", "free") else 0)
        + (20 if has("stop", "warning", "mistake", "scam", "dangerous", "wrong", "risk") else 0)
    )
    social = 30 + (15 if has("join", "million", "everyone", "insider", "exclusive", "first") else 0)
    practical = (
        30
        + (15 if re.search(r"\d", t) else 0)
        + (10 if has("%", "$", "how", "tips", "guide", "save", "fix", "minutes") else 0)
    )
    story = 30 + (20 if has("before", "after", "when", "until", "story", " i ", " my ") else 0)
    novelty = 40 + (15 if "?" in t else 0) + (10 if has("secret", "wrong", "myth", "nobody") else 0)
    triggers = 20 + (
        25 if has("morning", "monday", "summer", "holiday", "every day", "bed", "commute", "coffee") else 0
    )
    public = 20 + (25 if has("wear", "show", "notice", "look", "post", "share", "tag") else 0)

    dim = ViralityDimensions(
        arousal=min(100, arousal),
        social_currency=min(100, social),
        practical_value=min(100, practical),
        story=min(100, story),
        novelty=min(100, novelty),
        triggers=min(100, triggers),
        public_observability=min(100, public),
    )
    diagnostics = ViralityDiagnostics(
        # Short, punchy copy reads as clear; long copy loses the single hero claim.
        clarity=max(10, min(100, 85 - min(60, max(0, word_count - 12) * 2))),
        brand_prominence=min(100, 30 * len(re.findall(r"[®™©]", text or ""))),
    )

    best_id, best_name, strength = _best_pattern_match(t)
    conflicts = []
    if has(*_RISKY_AMPLIFIERS):
        conflicts.append("Absolute wording raises arousal but is the first thing compliance strikes.")

    review = ViralityReviewV2(
        dimensions=dim,
        diagnostics=diagnostics,
        closest_pattern_id=best_id,
        closest_pattern_name=best_name,
        pattern_match_strength=strength,
        suggestions=_offline_suggestions(t, strength, compliance_hits or []),
        summary=f"Offline Virality Index estimate; closest pattern: {best_name or 'none'}.",
        compliance_conflicts=conflicts,
    )
    stored = wrap_stored_virality(review)
    stored["scored_by"] = "heuristic"
    if compliance_hits:
        annotate_compliance_conflicts(stored, violations=list(compliance_hits))
    return stored


def _best_pattern_match(text: str) -> tuple[str | None, str | None, str]:
    words = set(re.findall(r"[a-z0-9']+", text))
    best_score = 0.0
    best = None
    for p in load_viral_patterns():
        sw = set(re.findall(r"[a-z0-9']+", str(p.get("snippet") or "").lower()))
        if not sw:
            continue
        overlap = len(words & sw) / len(sw)
        if overlap > best_score:
            best_score = overlap
            best = p
    if not best or best_score < 0.08:
        return None, None, "none"
    strength = "strong" if best_score >= 0.35 else "moderate" if best_score >= 0.18 else "weak"
    return str(best.get("id")), str(best.get("name")), strength


def _offline_suggestions(text: str, strength: str, hits: list[str]) -> list[str]:
    """Each suggestion names the dimension it is meant to lift."""
    sugs: list[str] = []
    if strength in ("none", "weak"):
        sugs.append("Novelty: open with a curiosity gap or a specific number in the first 8 words.")
    if not re.search(r"\d", text):
        sugs.append("Practical value: add one concrete stat, timeframe, or price anchor.")
    if not any(w in text for w in ("morning", "monday", "summer", "every day", "commute", "coffee")):
        sugs.append("Triggers: tie the ad to a recurring moment so it resurfaces on its own.")
    if not any(w in text for w in ("wear", "show", "notice", "post", "share")):
        sugs.append("Public observability: make the result something other people can see.")
    if len(text.split()) > 30:
        sugs.append("Clarity: shorten to one hero claim before adding more emotion.")
    if hits:
        sugs.append("Keep compliance fixes; raise arousal through story, not stronger guarantees.")
    if not sugs:
        sugs.append("A/B test a pattern-interrupt first line while keeping substantiation.")
    return sugs[:3]


def run_virality_in_memory(
    *,
    text: str,
    violations: list[Any] | None = None,
    compliance_status: str | None = None,
) -> dict[str, Any]:
    """
    Score ad copy. Gemini when enabled, else the offline heuristic.

    Safe to call from a worker thread: no DB session and no shared mutable state.
    ``violations`` is optional — when the pipeline runs this concurrently the verdict
    does not exist yet, and conflicts are attached later via
    :func:`annotate_compliance_conflicts`.
    """
    hits = _violation_labels(violations)
    if not virality_review_enabled():
        return score_virality_offline(text, compliance_hits=hits)

    payload = json.dumps(
        {
            "ad_copy": text[:8000],
            "compliance_status": compliance_status,
            "compliance_triggers": hits,
            "viral_pattern_library": patterns_for_prompt(),
        },
        ensure_ascii=False,
    )
    try:
        raw = gemini_mod.gemini_text_chat(
            payload,
            system_prompt=_SYSTEM,
            max_output_tokens=1200,
            temperature=0.3,
            response_mime_type="application/json",
        )
        stored = wrap_stored_virality(_parse_json(raw))
        stored["scored_by"] = "gemini"
    except BadViralityOutput:
        return score_virality_offline(text, compliance_hits=hits)
    except Exception:
        logger.exception("Virality LLM failed; using offline heuristic")
        return score_virality_offline(text, compliance_hits=hits)

    if hits or compliance_status:
        annotate_compliance_conflicts(
            stored, violations=list(hits), compliance_status=compliance_status
        )
    return stored


def _scoreable_text(asset: Any, verdict_result: dict[str, Any] | None) -> str:
    """Asset text, or the document text the pipeline derived from an image/PDF."""
    from zataone.core.pipeline_run import document_text

    return (getattr(asset, "content", None) or "").strip() or document_text(verdict_result)


def run_virality_review(session: Session, asset_id: UUID) -> dict[str, Any]:
    """On-demand scoring for a stored asset; uses the persisted verdict for conflicts."""
    asset = session.query(AssetModel).filter(AssetModel.id == asset_id).first()
    if asset is None:
        raise AssetNotReadyForViralityReview("Asset not found")

    verdict = _latest_verdict(session, asset_id)
    result = dict(verdict.result) if verdict and isinstance(verdict.result, dict) else {}

    text = _scoreable_text(asset, result)
    if not text:
        raise AssetNotReadyForViralityReview(
            "Virality Index needs ad copy; this asset has no text and no extracted document text"
        )

    stored = run_virality_in_memory(
        text=text,
        violations=list(result.get("violations") or []),
        compliance_status=result.get("status") or result.get("compliance_status"),
    )
    merge_verdict_with_virality(session, asset_id, stored)
    return stored


def _latest_verdict(session: Session, asset_id: UUID) -> Any:
    return (
        session.query(VerdictModel)
        .filter(VerdictModel.asset_id == asset_id)
        .order_by(VerdictModel.created_at.desc())
        .first()
    )


def merge_verdict_with_virality(
    session: Session,
    asset_id: UUID,
    stored: dict[str, Any],
) -> None:
    verdict = _latest_verdict(session, asset_id)
    if verdict is None:
        raise AssetNotReadyForViralityReview("Verdict not found")
    base: dict[str, Any] = dict(verdict.result) if isinstance(verdict.result, dict) else {}
    base["virality_index"] = stored
    verdict.result = base
    session.add(verdict)
