# zataone pipeline run helpers — extraction, VLM-primary image path, advisory

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from zataone.core.extractor_flags import (
    pipeline_auto_advisory_enabled,
    pipeline_parallel_extractors_enabled,
    pipeline_parallel_vlm_enabled,
    vlm_primary_image_path,
)
from zataone.core.pipeline_progress import update as progress_update

logger = logging.getLogger(__name__)


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
