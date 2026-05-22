# zataone API routes

import asyncio
import json
import os
import re
import uuid
from types import SimpleNamespace
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, File, Header, HTTPException, Path, UploadFile
from pydantic import BaseModel, Field

from zataone.core.pipeline import CompliancePipeline, resolve_pipeline_mode
from zataone.core.verdict_display import enrich_api_verdict_payload
from zataone.models import (
    Asset as AssetModel,
    Evidence as EvidenceModel,
    Signal as SignalModel,
    Verdict as VerdictModel,
    Violation as ViolationModel,
)
from zataone.services.ingestion_service import IngestionService
from zataone.services.llm_final_review_service import (
    AssetNotReadyForLlmReview,
    BadLlmReviewOutput,
    merge_verdict_with_llm_review,
    run_llm_final_review,
)
from zataone.storage.database import get_session_factory

router = APIRouter()

_DOMAIN_RE = re.compile(r"^[a-z0-9_]+$")


def _resolve_domain(x_domain: str | None) -> str:
    """
    Resolve pipeline domain from optional X-Domain header.

    Env:
      ZATAONE_DEFAULT_DOMAIN — used when header is absent (default: ad_compliance).
      ZATAONE_ALLOWED_DOMAINS — comma-separated allowlist; if unset, only the default domain is allowed.
    The default domain is always permitted even if omitted from the explicit list.
    """
    default = (os.environ.get("ZATAONE_DEFAULT_DOMAIN") or "ad_compliance").strip() or "ad_compliance"
    default_l = default.lower()
    raw = (os.environ.get("ZATAONE_ALLOWED_DOMAINS") or "").strip()
    if raw:
        allowed = {p.strip().lower() for p in raw.split(",") if p.strip()}
    else:
        allowed = {default_l}
    allowed.add(default_l)

    req = (x_domain or "").strip().lower()
    if not req:
        req = default_l
    if not _DOMAIN_RE.match(req):
        raise HTTPException(status_code=400, detail="Invalid X-Domain")
    if req not in allowed:
        raise HTTPException(status_code=403, detail=f"Domain not allowed: {req}")
    return req


def _use_sync_pipeline() -> bool:
    """
    Run the compliance pipeline in the POST request (not BackgroundTasks).

    Cloud Run throttles CPU after the response unless configured otherwise, so
    background tasks often never finish. Cloud Run sets K_SERVICE; we default to
    sync there. Override with ZATAONE_ASYNC_PIPELINE=true or ZATAONE_SYNC_PIPELINE=false.
    """
    if os.environ.get("ZATAONE_ASYNC_PIPELINE", "").lower() in ("1", "true", "yes"):
        return False
    if os.environ.get("ZATAONE_SYNC_PIPELINE", "").lower() in ("0", "false", "no"):
        return False
    if os.environ.get("ZATAONE_SYNC_PIPELINE", "").lower() in ("1", "true", "yes"):
        return True
    return bool(os.environ.get("K_SERVICE"))


def _asset_status_dict(session: Any, asset_id: uuid.UUID) -> dict[str, Any] | None:
    """Build GET /assets/{id} payload, or None if asset missing."""
    asset = session.query(AssetModel).filter(AssetModel.id == asset_id).first()
    if asset is None:
        return None

    if asset.status == "processing":
        from zataone.core.pipeline_progress import get as pipeline_progress_get

        return {
            "status": "processing",
            "asset_id": str(asset_id),
            "pipeline_progress": pipeline_progress_get(str(asset_id)) or {},
        }

    if asset.status == "failed":
        return {
            "status": "failed",
            "asset_id": str(asset_id),
            "detail": "Compliance pipeline did not complete; see Cloud Run logs.",
        }

    verdict = (
        session.query(VerdictModel)
        .filter(VerdictModel.asset_id == asset_id)
        .order_by(VerdictModel.created_at.desc())
        .first()
    )
    if verdict is None:
        return {"status": asset.status, "asset_id": str(asset_id)}

    result = dict(verdict.result)
    verdict_formatted = _format_verdict_response(result)
    compliance_status = verdict_formatted.pop("status", "")
    meta = verdict_formatted.get("metadata") or {}
    out = {
        "status": "completed",
        "asset_id": str(asset_id),
        "compliance_status": compliance_status,
        **verdict_formatted,
    }
    if result.get("llm_final_review"):
        out["llm_final_review"] = result["llm_final_review"]
    if meta.get("advisory_vlm"):
        out["advisory_vlm"] = meta["advisory_vlm"]
    if meta.get("pipeline_progress"):
        out["pipeline_progress"] = meta["pipeline_progress"]
    return out


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class AssetCreateRequest(BaseModel):
    """Request body for POST /assets."""

    content: str = Field(..., description="Asset content (text or base64 for binary)")
    type: Literal["text", "image", "video", "audio"] = Field(
        ..., description="Asset type"
    )
    asset_id: str | None = Field(None, description="Optional asset identifier")
    metadata: dict[str, Any] | None = Field(None, description="Optional metadata")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _pipeline_mode_header(x_pipeline_mode: str | None) -> str | None:
    if x_pipeline_mode and x_pipeline_mode.strip().lower() in ("fast", "full"):
        return x_pipeline_mode.strip().lower()
    return None


def _format_verdict_response(result: dict[str, Any]) -> dict[str, Any]:
    """Format pipeline verdict as API response."""
    formatted = {
        "verdict": result.get("verdict", ""),
        "risk_score": result.get("risk_score", 0.0),
        "status": result.get("status", ""),
        "violations": result.get("violations", []),
        "signals": result.get("signals", []),
        "fix_suggestions": result.get("fix_suggestions", []),
        "metadata": result.get("metadata", {}),
    }
    return enrich_api_verdict_payload(formatted)


def _run_pipeline_background(
    asset: Any,
    asset_id: uuid.UUID,
    tenant_id: str | None,
    idempotency_key: str | None,
    domain: str,
    pipeline_mode: str | None = None,
) -> None:
    """Background task: run pipeline and persist result to existing asset."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        pipeline = CompliancePipeline(domain=domain)
        pipeline.run(
            asset,
            tenant_id=tenant_id,
            persist=True,
            idempotency_key=idempotency_key,
            existing_asset_id=asset_id,
            pipeline_mode=pipeline_mode,
        )
        logger.info("Background pipeline completed for asset %s", asset_id)
    except Exception as e:
        logger.exception("Background pipeline failed for asset %s: %s", asset_id, e)
        session = get_session_factory()()
        try:
            IngestionService().set_asset_status(session, asset_id, "failed")
        except Exception:
            logger.exception("Could not mark asset %s as failed", asset_id)
        finally:
            session.close()


@router.post("/assets")
def post_assets(
    background_tasks: BackgroundTasks,
    body: AssetCreateRequest,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    x_domain: str | None = Header(None, alias="X-Domain"),
    x_pipeline_mode: str | None = Header(None, alias="X-Pipeline-Mode"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """
    Run compliance check on an asset (async).

    Returns immediately with status: processing and asset_id.
    Poll GET /assets/{asset_id} for the verdict when ready.

    Optional Idempotency-Key: if provided and an asset with the same key exists,
    returns the existing verdict without re-running the pipeline.
    """
    domain = _resolve_domain(x_domain)
    pm = _pipeline_mode_header(x_pipeline_mode)
    if idempotency_key:
        session = get_session_factory()()
        try:
            ingestion = IngestionService()
            existing = ingestion.find_existing_verdict(
                session, idempotency_key, tenant_id=x_tenant_id
            )
            if existing:
                eid, eresult = existing
                out = _format_verdict_response(eresult)
                out["asset_id"] = str(eid)
                return out
        finally:
            session.close()

    asset = SimpleNamespace(
        asset_id=body.asset_id,
        content=body.content,
        type=body.type,
        metadata=body.metadata or {},
    )

    asset_id = uuid.uuid4()
    session = get_session_factory()()
    try:
        ingestion = IngestionService()
        ingestion.create_asset_stub(
            session,
            asset,
            asset_id=asset_id,
            tenant_id=x_tenant_id,
            idempotency_key=idempotency_key,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()

    if _use_sync_pipeline():
        try:
            CompliancePipeline(domain=domain).run(
                asset,
                tenant_id=x_tenant_id,
                persist=True,
                idempotency_key=idempotency_key,
                existing_asset_id=asset_id,
                pipeline_mode=pm,
            )
        except Exception as e:
            session = get_session_factory()()
            try:
                IngestionService().set_asset_status(session, asset_id, "failed")
            finally:
                session.close()
            raise HTTPException(status_code=500, detail=str(e)) from e
        session = get_session_factory()()
        try:
            out = _asset_status_dict(session, asset_id)
            if out is None:
                raise HTTPException(status_code=404, detail="Asset not found")
            return out
        finally:
            session.close()

    background_tasks.add_task(
        _run_pipeline_background,
        asset,
        asset_id,
        x_tenant_id,
        idempotency_key,
        domain,
        pm,
    )

    return {"status": "processing", "asset_id": str(asset_id), "pipeline_mode": resolve_pipeline_mode(pm)}


@router.post("/assets/image")
async def post_assets_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    x_domain: str | None = Header(None, alias="X-Domain"),
    x_pipeline_mode: str | None = Header(None, alias="X-Pipeline-Mode"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """
    Run compliance check on an uploaded image (async).

    Returns immediately with status: processing and asset_id.
    Poll GET /assets/{asset_id} for the verdict when ready.

    Optional Idempotency-Key: if provided and an asset with the same key exists,
    returns the existing verdict without re-running the pipeline.
    """
    domain = _resolve_domain(x_domain)
    pm = _pipeline_mode_header(x_pipeline_mode)
    if idempotency_key:
        session = get_session_factory()()
        try:
            ingestion = IngestionService()
            existing = ingestion.find_existing_verdict(
                session, idempotency_key, tenant_id=x_tenant_id
            )
            if existing:
                eid, eresult = existing
                out = _format_verdict_response(eresult)
                out["asset_id"] = str(eid)
                return out
        finally:
            session.close()

    try:
        image_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}") from e

    asset = SimpleNamespace(
        asset_id=None,
        content=None,
        image_data=image_bytes,
        type="image",
    )

    asset_id = uuid.uuid4()
    session = get_session_factory()()
    try:
        ingestion = IngestionService()
        ingestion.create_asset_stub(
            session,
            asset,
            asset_id=asset_id,
            tenant_id=x_tenant_id,
            idempotency_key=idempotency_key,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()

    if _use_sync_pipeline():

        def _run_img_pipeline() -> None:
            CompliancePipeline(domain=domain).run(
                asset,
                tenant_id=x_tenant_id,
                persist=True,
                idempotency_key=idempotency_key,
                existing_asset_id=asset_id,
                pipeline_mode=pm,
            )

        try:
            await asyncio.to_thread(_run_img_pipeline)
        except Exception as e:
            session = get_session_factory()()
            try:
                IngestionService().set_asset_status(session, asset_id, "failed")
            finally:
                session.close()
            raise HTTPException(status_code=500, detail=str(e)) from e
        session = get_session_factory()()
        try:
            out = _asset_status_dict(session, asset_id)
            if out is None:
                raise HTTPException(status_code=404, detail="Asset not found")
            return out
        finally:
            session.close()

    background_tasks.add_task(
        _run_pipeline_background,
        asset,
        asset_id,
        x_tenant_id,
        idempotency_key,
        domain,
        pm,
    )

    return {"status": "processing", "asset_id": str(asset_id), "pipeline_mode": resolve_pipeline_mode(pm)}


@router.post("/assets/audio")
async def post_assets_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-ID"),
    x_domain: str | None = Header(None, alias="X-Domain"),
    x_pipeline_mode: str | None = Header(None, alias="X-Pipeline-Mode"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """
    Run compliance check on uploaded audio: transcribe with Whisper (faster-whisper), then policy on text.

    Poll GET /assets/{asset_id} for the verdict when async; sync on Cloud Run (see _use_sync_pipeline).
    """
    domain = _resolve_domain(x_domain)
    pm = _pipeline_mode_header(x_pipeline_mode)
    if idempotency_key:
        session = get_session_factory()()
        try:
            ingestion = IngestionService()
            existing = ingestion.find_existing_verdict(
                session, idempotency_key, tenant_id=x_tenant_id
            )
            if existing:
                eid, eresult = existing
                out = _format_verdict_response(eresult)
                out["asset_id"] = str(eid)
                return out
        finally:
            session.close()

    try:
        audio_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}") from e

    asset = SimpleNamespace(
        asset_id=None,
        content=None,
        audio_data=audio_bytes,
        audio_filename=file.filename or "audio.wav",
        type="audio",
    )

    asset_id = uuid.uuid4()
    session = get_session_factory()()
    try:
        ingestion = IngestionService()
        ingestion.create_asset_stub(
            session,
            asset,
            asset_id=asset_id,
            tenant_id=x_tenant_id,
            idempotency_key=idempotency_key,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()

    if _use_sync_pipeline():

        def _run_audio_pipeline() -> None:
            CompliancePipeline(domain=domain).run(
                asset,
                tenant_id=x_tenant_id,
                persist=True,
                idempotency_key=idempotency_key,
                existing_asset_id=asset_id,
                pipeline_mode=pm,
            )

        try:
            await asyncio.to_thread(_run_audio_pipeline)
        except Exception as e:
            session = get_session_factory()()
            try:
                IngestionService().set_asset_status(session, asset_id, "failed")
            finally:
                session.close()
            raise HTTPException(status_code=500, detail=str(e)) from e
        session = get_session_factory()()
        try:
            out = _asset_status_dict(session, asset_id)
            if out is None:
                raise HTTPException(status_code=404, detail="Asset not found")
            return out
        finally:
            session.close()

    background_tasks.add_task(
        _run_pipeline_background,
        asset,
        asset_id,
        x_tenant_id,
        idempotency_key,
        domain,
        pm,
    )

    return {"status": "processing", "asset_id": str(asset_id), "pipeline_mode": resolve_pipeline_mode(pm)}


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: uuid.UUID = Path(..., description="Asset ID from POST response"),
) -> dict[str, Any]:
    """
    Get asset status and verdict.

    Returns status: processing while the compliance check runs, or status: completed
    with verdict, risk_score, violations, etc. when done.
    """
    session = get_session_factory()()
    try:
        out = _asset_status_dict(session, asset_id)
        if out is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        return out
    finally:
        session.close()


def _model_to_dict(obj: Any, exclude: set[str] | None = None) -> dict[str, Any]:
    """Convert SQLAlchemy model to JSON-serializable dict."""
    if obj is None:
        return {}
    exclude = exclude or set()
    d = {}
    for c in obj.__table__.columns:
        if c.name in exclude:
            continue
        val = getattr(obj, c.name)
        if hasattr(val, "hex"):
            d[c.name] = str(val)
        elif hasattr(val, "isoformat"):
            d[c.name] = val.isoformat()
        else:
            d[c.name] = val
    return d


@router.post("/assets/{asset_id}/llm-final-review")
async def post_llm_final_review(
    asset_id: uuid.UUID = Path(..., description="Asset with completed compliance verdict"),
    file: UploadFile | None = File(None),
    x_domain: str | None = Header(None, alias="X-Domain"),
) -> dict[str, Any]:
    """
    Optional advisory pass: load deterministic signals + verdict from DB, optionally VLM
    summary of an **uploaded** image, then one Gemini call. Does not replace the policy verdict.
    Re-upload the same image in `file` for best VLM+signals alignment (blobs are not stored on the asset).
    """
    domain = _resolve_domain(x_domain)
    image_bytes: bytes | None = None
    if file and file.filename:
        try:
            image_bytes = await file.read()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to read file: {e}") from e

    session = get_session_factory()()
    try:
        try:
            stored, vlm_status = run_llm_final_review(
                session, asset_id, domain=domain, image_bytes=image_bytes
            )
        except AssetNotReadyForLlmReview as e:
            msg = str(e)
            code = 404 if "not found" in msg.lower() else 400
            raise HTTPException(status_code=code, detail=msg) from e
        except BadLlmReviewOutput as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e)) from e

        merge_verdict_with_llm_review(session, asset_id, stored)
        session.commit()
        v = (
            session.query(VerdictModel)
            .filter(VerdictModel.asset_id == asset_id)
            .order_by(VerdictModel.created_at.desc())
            .first()
        )
        return {
            "llm_final_review": stored,
            "verdict": dict(v.result) if v and v.result else {},
            "advisory_vlm": vlm_status,
        }
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()


@router.get("/assets/{asset_id}/graph")
def get_asset_graph(
    asset_id: uuid.UUID = Path(..., description="Asset ID"),
) -> dict[str, Any]:
    """
    Get full evidence graph for an asset.

    Returns asset, signals, violations, evidence, verdict.
    """
    session = get_session_factory()()
    try:
        asset = session.query(AssetModel).filter(AssetModel.id == asset_id).first()
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")

        signals = session.query(SignalModel).filter(SignalModel.asset_id == asset_id).all()
        violations = (
            session.query(ViolationModel).filter(ViolationModel.asset_id == asset_id).all()
        )
        evidence = session.query(EvidenceModel).filter(EvidenceModel.asset_id == asset_id).all()
        verdict = (
            session.query(VerdictModel)
            .filter(VerdictModel.asset_id == asset_id)
            .order_by(VerdictModel.created_at.desc())
            .first()
        )

        verdict_dict = _model_to_dict(verdict) if verdict else {}
        verdict_result = verdict_dict.get("result") or {}
        meta = verdict_result.get("metadata") or {} if isinstance(verdict_result, dict) else {}
        document = meta.get("document")
        document_centric = meta.get("document_centric_enabled")
        policy_pack = meta.get("policy_pack")
        retrieval = meta.get("retrieval")

        return {
            "asset": _model_to_dict(asset),
            "document": document,
            "document_centric_enabled": document_centric,
            "policy_pack": policy_pack,
            "retrieval": retrieval,
            "signals": [_model_to_dict(s) for s in signals],
            "violations": [_model_to_dict(v) for v in violations],
            "evidence": [_model_to_dict(e) for e in evidence],
            "verdict": verdict_dict,
        }
    finally:
        session.close()
