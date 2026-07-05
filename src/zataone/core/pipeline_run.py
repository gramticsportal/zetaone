# zataone pipeline run helpers — parallel extraction and advisory orchestration

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from zataone.core.extractor_flags import (
    pipeline_auto_advisory_enabled,
    pipeline_parallel_extractors_enabled,
    pipeline_parallel_vlm_enabled,
)
from zataone.core.extractor_plan import select_extractors_for_asset
from zataone.core.pipeline_progress import update as progress_update
from zataone.document.builder import DocumentBuilder
from zataone.document.flags import document_centric_enabled
from zataone.extractors.base import BaseExtractor
from zataone.policy_engine.retrieval.flags import policy_retrieval_enabled

logger = logging.getLogger(__name__)


def extract_signals_parallel(
    extractors: list[BaseExtractor],
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


def run_parallel_vlm_and_deterministic(
    *,
    asset: Any,
    image_bytes: bytes | None,
    domain: str,
    asset_id: str | None,
    deterministic_fn,
) -> tuple[Any, dict[str, Any] | None, dict[str, Any]]:
    """
    Run deterministic_fn() in parallel with Gemini VLM (images only).

    Returns (deterministic_result, vlm_status, timing_ms dict).
    """
    from zataone.services.llm_final_review_service import run_gemini_vlm_inspection

    asset_type = getattr(asset, "type", None) or "text"
    run_vlm = (
        pipeline_parallel_vlm_enabled()
        and asset_type == "image"
        and bool(image_bytes)
        and pipeline_auto_advisory_enabled()
    )

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
            vlm_summary, vlm_error, vlm_status = fut_vlm.result()
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
