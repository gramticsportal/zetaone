# zataone pipeline run helpers — extraction, VLM-primary image path, advisory

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from typing import Any, Callable

from zataone.core.extractor_flags import (
    pipeline_auto_advisory_enabled,
    pipeline_parallel_extractors_enabled,
    pipeline_parallel_vlm_enabled,
    virality_extracted_join_timeout_ms,
    virality_join_timeout_ms,
    virality_review_enabled,
    vlm_primary_image_path,
)
from zataone.core.pipeline_progress import update as progress_update

logger = logging.getLogger(__name__)

# A deferred virality score races the pipeline's own verdict commit.
_LATE_PERSIST_ATTEMPTS = 6
_LATE_PERSIST_DELAY_S = 0.25


def extract_signals_parallel(
    extractors: list[Any],
    asset: Any,
    *,
    asset_id: str | None = None,
) -> tuple[list[Any], dict[str, int], dict[str, str]]:
    """
    Run extractors; parallel when enabled.

    Returns (signals, counts, failed) — failed maps extractor_id → error string
    for extractors that raised, so the pipeline can degrade the verdict instead
    of silently approving with missing coverage.
    """
    from zataone.extractors.base import BaseExtractor

    if asset_id:
        progress_update(asset_id, extraction="running")

    if not extractors:
        if asset_id:
            progress_update(asset_id, extraction="completed", signal_count=0)
        return [], {}, {}

    signals: list[Any] = []
    counts: dict[str, int] = {}
    failed: dict[str, str] = {}

    def _run_one(ext: BaseExtractor) -> tuple[str, list[Any], str | None]:
        eid = getattr(ext, "extractor_id", None) or type(ext).__name__
        try:
            return eid, list(ext.extract(asset) or []), None
        except Exception as e:
            logger.exception("Extractor failed: id=%s", eid)
            return eid, [], f"{type(e).__name__}: {e}"[:500]

    if pipeline_parallel_extractors_enabled() and len(extractors) > 1:
        max_workers = min(len(extractors), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_run_one, ext): ext for ext in extractors}
            for fut in as_completed(futures):
                eid, extracted, err = fut.result()
                counts[eid] = len(extracted)
                if err:
                    failed[eid] = err
                if extracted:
                    signals.extend(extracted)
    else:
        for ext in extractors:
            eid, extracted, err = _run_one(ext)
            counts[eid] = len(extracted)
            if err:
                failed[eid] = err
            if extracted:
                signals.extend(extracted)

    if asset_id:
        progress_update(
            asset_id,
            extraction="completed",
            signal_count=len(signals),
            extractor_counts=counts,
            extractor_failures=sorted(failed) or None,
        )
    return signals, counts, failed


def run_vlm_then_deterministic(
    *,
    asset: Any,
    image_bytes: bytes,
    domain: str,
    asset_id: str | None,
    deterministic_fn: Callable[..., Any],
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """
    VLM-primary image path: structured Gemini VLM → matcher signals → hybrid/rules.

    deterministic_fn must accept pre_signals=list.
    """
    from zataone.document.vlm_packet import structured_to_matcher_signals
    from zataone.services.llm_final_review_service import run_gemini_vlm_inspection

    if asset_id:
        progress_update(asset_id, vlm="running", deterministic="running")

    timing: dict[str, Any] = {}
    t0 = time.perf_counter()
    _summary, vlm_error, vlm_status = run_gemini_vlm_inspection(
        image_bytes,
        domain=domain,
        det={"status": "PROCESSING", "verdict": "pending", "risk_score": None},
    )
    timing["vlm_ms"] = round((time.perf_counter() - t0) * 1000)
    if asset_id:
        progress_update(
            asset_id,
            vlm="completed" if vlm_status.get("vlm_succeeded") else "failed",
            vlm_error=vlm_error,
        )

    pre_signals = structured_to_matcher_signals(vlm_status.get("structured"))
    t1 = time.perf_counter()
    det_result = deterministic_fn(pre_signals=pre_signals)
    timing["deterministic_ms"] = round((time.perf_counter() - t1) * 1000)
    if asset_id:
        progress_update(asset_id, deterministic="completed")

    meta = (det_result.get("verdict") or {}).setdefault("metadata", {})
    meta["vlm_primary_image_path"] = True
    meta["vlm_matcher_signal_count"] = len(pre_signals)
    return det_result, vlm_status, timing


def run_parallel_vlm_and_deterministic(
    *,
    asset: Any,
    image_bytes: bytes | None,
    domain: str,
    asset_id: str | None,
    deterministic_fn: Callable[..., Any],
) -> tuple[Any, dict[str, Any] | None, dict[str, Any]]:
    """
    Image Full path orchestration.

    - Default (OCR+DINO off): VLM first, then deterministic with VLM matcher signals.
    - Legacy parallel: when OCR/DINO enabled and ZATAONE_PARALLEL_VLM=1.
    """
    from zataone.services.llm_final_review_service import run_gemini_vlm_inspection

    asset_type = getattr(asset, "type", None) or "text"
    can_vlm = (
        asset_type == "image"
        and bool(image_bytes)
        and pipeline_auto_advisory_enabled()
    )

    if can_vlm and vlm_primary_image_path():
        return run_vlm_then_deterministic(
            asset=asset,
            image_bytes=image_bytes,  # type: ignore[arg-type]
            domain=domain,
            asset_id=asset_id,
            deterministic_fn=deterministic_fn,
        )

    run_vlm = can_vlm and pipeline_parallel_vlm_enabled()

    if asset_id:
        progress_update(asset_id, deterministic="running")
        if run_vlm:
            progress_update(asset_id, vlm="running")

    timing: dict[str, Any] = {}
    vlm_status: dict[str, Any] | None = None
    det_result = None

    if run_vlm:
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_det = pool.submit(deterministic_fn)
            fut_vlm = pool.submit(
                run_gemini_vlm_inspection,
                image_bytes,
                domain=domain,
                det={"status": "PROCESSING", "verdict": "pending", "risk_score": None},
            )
            _vlm_summary, vlm_error, vlm_status = fut_vlm.result()
            timing["vlm_ms"] = round((time.perf_counter() - t0) * 1000)
            if asset_id:
                progress_update(
                    asset_id,
                    vlm="completed" if vlm_status.get("vlm_succeeded") else "failed",
                    vlm_error=vlm_error,
                )
            det_result = fut_det.result()
            timing["deterministic_ms"] = round((time.perf_counter() - t0) * 1000)
    else:
        t0 = time.perf_counter()
        det_result = deterministic_fn()
        timing["deterministic_ms"] = round((time.perf_counter() - t0) * 1000)
        if asset_id:
            progress_update(asset_id, vlm="skipped", vlm_skipped_reason="not_image_or_no_key")

    if asset_id:
        progress_update(asset_id, deterministic="completed")

    return det_result, vlm_status, timing


def maybe_run_pipeline_advisory(
    *,
    domain: str,
    asset: Any,
    asset_id: str | None,
    det_bundle: dict[str, Any],
    vlm_status: dict[str, Any] | None,
    image_bytes: bytes | None,
) -> dict[str, Any] | None:
    """Gemini text advisory after deterministic verdict; does not change compliance_status."""
    if (det_bundle["verdict"].get("metadata") or {}).get("fast_combined_review"):
        return det_bundle["verdict"].get("llm_final_review")
    if not pipeline_auto_advisory_enabled():
        if asset_id:
            progress_update(asset_id, advisory="skipped", advisory_skipped_reason="disabled")
        return None

    from zataone.services.llm_final_review_service import run_advisory_synthesis_in_memory

    if asset_id:
        progress_update(asset_id, advisory="running")

    try:
        stored, vlm_out = run_advisory_synthesis_in_memory(
            domain=domain,
            asset=asset,
            asset_id=asset_id,
            verdict=det_bundle["verdict"],
            signals=det_bundle["signals"],
            violations=det_bundle.get("violations_raw") or [],
            vlm_status=vlm_status,
            image_bytes=image_bytes,
        )
        if asset_id:
            progress_update(asset_id, advisory="completed")
        det_bundle["verdict"]["llm_final_review"] = stored
        meta = det_bundle["verdict"].setdefault("metadata", {})
        meta["advisory_vlm"] = vlm_out
        meta["pipeline_advisory"] = True
        return stored
    except Exception as e:
        logger.exception("Pipeline advisory failed: %s", e)
        if asset_id:
            progress_update(asset_id, advisory="failed", advisory_error=str(e)[:500])
        return None


class ViralityTask:
    """
    In-flight Virality Index scoring, started before the compliance path.

    Virality depends only on the ad copy, so the LLM call overlaps extraction, VLM,
    the rule engine and the compliance advisory. :meth:`join` collects it under a short
    grace period; anything still outstanding is written to the verdict row by the worker
    itself, so the request never waits on it and the API call is never wasted.
    """

    def __init__(
        self,
        pool: ThreadPoolExecutor,
        future: Any,
        asset_id: str | None,
        join_timeout_ms: int | None = None,
    ) -> None:
        self._pool = pool
        self._future = future
        self._asset_id = asset_id
        self._started = time.perf_counter()
        self._join_timeout_ms = (
            virality_join_timeout_ms() if join_timeout_ms is None else max(0, join_timeout_ms)
        )

    def join(self, det_bundle: dict[str, Any]) -> dict[str, Any] | None:
        """Attach the score to the verdict on the main thread; never raises."""
        from zataone.services.virality_review_service import annotate_compliance_conflicts

        verdict = det_bundle["verdict"]
        meta = verdict.setdefault("metadata", {})
        budget_s = self._join_timeout_ms / 1000.0
        waited_s = time.perf_counter() - self._started

        try:
            stored = self._future.result(timeout=budget_s)
        except FuturesTimeout:
            # Do not pay for the rest of the call. Let the worker finish and write the
            # score straight to the verdict row so the request stays latency-neutral
            # and the API call is not wasted.
            self._defer_persist()
            self._pool.shutdown(wait=False)
            meta["virality_pending"] = True
            if self._asset_id:
                progress_update(
                    self._asset_id, virality="pending", virality_skipped_reason="timeout"
                )
            logger.info(
                "Virality still in flight after %.0fms budget; persisting asynchronously",
                budget_s * 1000,
            )
            return None
        except Exception as e:
            self._pool.shutdown(wait=False)
            logger.exception("Virality review failed: %s", e)
            if self._asset_id:
                progress_update(self._asset_id, virality="failed", virality_error=str(e)[:500])
            return None

        self._pool.shutdown(wait=False)
        annotate_compliance_conflicts(
            stored,
            violations=det_bundle.get("violations_raw") or verdict.get("violations") or [],
            compliance_status=verdict.get("status"),
        )
        verdict["virality_index"] = stored
        meta["virality_review"] = True
        meta["virality_overlapped_ms"] = round(waited_s * 1000)
        if self._asset_id:
            progress_update(self._asset_id, virality="completed")
        return stored

    def _defer_persist(self) -> None:
        """Write a late score to the verdict row once the worker finishes."""
        if not self._asset_id:
            return
        asset_id = self._asset_id

        def _on_done(fut: Any) -> None:
            try:
                stored = fut.result()
            except Exception:
                logger.exception("Deferred virality scoring failed for asset %s", asset_id)
                return
            if _persist_late_virality(asset_id, stored):
                progress_update(asset_id, virality="completed_deferred")

        self._future.add_done_callback(_on_done)


def _persist_late_virality(asset_id: str, stored: dict[str, Any]) -> bool:
    """Attach a deferred score, waiting briefly for the verdict row to be committed."""
    from uuid import UUID

    from zataone.services.virality_review_service import (
        AssetNotReadyForViralityReview,
        merge_verdict_with_virality,
    )
    from zataone.storage.database import get_session_factory

    for attempt in range(_LATE_PERSIST_ATTEMPTS):
        session = get_session_factory()()
        try:
            merge_verdict_with_virality(session, UUID(asset_id), stored)
            session.commit()
            return True
        except AssetNotReadyForViralityReview:
            session.rollback()
            time.sleep(_LATE_PERSIST_DELAY_S * (attempt + 1))
        except Exception:
            session.rollback()
            logger.exception("Could not persist deferred virality for asset %s", asset_id)
            return False
        finally:
            session.close()
    logger.info("Deferred virality dropped for asset %s; no verdict row appeared", asset_id)
    return False


def document_text(
    verdict: dict[str, Any] | None,
    vlm_status: dict[str, Any] | None = None,
) -> str:
    """
    Scoreable copy for an asset: native text, then the VLM's reading of an image.

    Prefers the structured VLM packet (OCR + claims + scene) over a raw JSON dump,
    because that is what the vision model actually understood about the creative.
    """
    meta = (verdict or {}).get("metadata") or {}
    vlm = vlm_status if isinstance(vlm_status, dict) else None
    if vlm is None:
        vlm = meta.get("advisory_vlm") if isinstance(meta.get("advisory_vlm"), dict) else None

    structured = (vlm or {}).get("structured") if vlm else None
    if isinstance(structured, dict) and structured:
        from zataone.document.vlm_packet import inspection_summary_for_llm

        summary = inspection_summary_for_llm(structured)
        if summary:
            return summary[:12000]

    inspection = (vlm or {}).get("inspection") if vlm else None
    if isinstance(inspection, str) and inspection.strip():
        return inspection.strip()[:12000]

    doc = meta.get("document") or {}
    if isinstance(doc, dict):
        return str(doc.get("normalized_text") or "").strip()
    return ""


def start_virality_review(
    *,
    asset: Any,
    asset_id: str | None,
    extracted_text: str | None = None,
) -> ViralityTask | None:
    """
    Kick off the Virality Index concurrently with the compliance pipeline.

    Every modality gets scored, but they start at different points. A text asset starts
    immediately from ``asset.content``, overlapping the whole compliance path. An image or
    PDF has no copy until extraction runs, so it starts once the caller can pass the VLM/OCR
    document text as ``extracted_text`` — early enough to still overlap the advisory LLM call.

    ``extracted_text`` also marks the attempt as final: the speculative pre-extraction call
    stays quiet when there is no copy yet, so progress only reports a skip once we know no
    copy is coming.
    """
    from zataone.services.virality_review_service import run_virality_in_memory

    final_attempt = extracted_text is not None

    if not virality_review_enabled():
        if asset_id:
            progress_update(asset_id, virality="skipped", virality_skipped_reason="disabled")
        return None

    text = (getattr(asset, "content", None) or "").strip() or (extracted_text or "").strip()
    if not text:
        if asset_id and final_attempt:
            progress_update(asset_id, virality="skipped", virality_skipped_reason="no_copy_found")
        return None

    if asset_id:
        progress_update(asset_id, virality="running")
    # Image/PDF copy only exists after the VLM, so this call starts late. Wait for it
    # in-request: Cloud Run freezes deferred work the moment the response is sent.
    has_native = bool((getattr(asset, "content", None) or "").strip())
    join_ms = (
        virality_join_timeout_ms()
        if has_native
        else virality_extracted_join_timeout_ms()
    )
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="virality")
    future = pool.submit(run_virality_in_memory, text=text)
    return ViralityTask(pool, future, asset_id, join_timeout_ms=join_ms)
