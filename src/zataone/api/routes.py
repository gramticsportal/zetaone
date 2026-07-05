# zataone API routes

from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
)
from pydantic import BaseModel, Field

from zataone.api.auth import AuthContext, get_auth_context
from zataone.core.pipeline import CompliancePipeline, resolve_pipeline_mode
from zataone.policy_engine.jurisdiction.router import JurisdictionRouter as _JR
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
from zataone.services.review_service import ReviewService, decision_to_dict
from zataone.storage.database import get_session_factory
from zataone.storage.object_store import ObjectStore

logger = logging.getLogger(__name__)

router = APIRouter()

_DOMAIN_RE = re.compile(r"^[a-z0-9_]+$")

# Pipeline singleton cache: one CompliancePipeline per domain, created once at first use.
# Avoids YAML + module loading + AST compilation on every request.
_pipeline_cache: dict[str, "CompliancePipeline"] = {}
_pipeline_cache_lock = threading.Lock()


def _get_pipeline(domain: str, jurisdiction: str = "US") -> "CompliancePipeline":
    j = _JR().normalize(jurisdiction)
    key = f"{domain}:{j}"
    if key not in _pipeline_cache:
        with _pipeline_cache_lock:
            if key not in _pipeline_cache:
                _pipeline_cache[key] = CompliancePipeline(domain=domain, jurisdiction=j)
    return _pipeline_cache[key]


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


def _asset_common_fields(asset: Any) -> dict[str, Any]:
    """Lineage / review / media fields shared by status and list payloads."""
    return {
        "review_state": asset.review_state,
        "external_ref": asset.external_ref,
        "parent_asset_id": str(asset.parent_asset_id) if asset.parent_asset_id else None,
        "media_url": f"/assets/{asset.id}/media" if asset.storage_uri else None,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def _asset_status_dict(session: Any, asset_id: uuid.UUID) -> dict[str, Any] | None:
    """Build GET /assets/{id} payload, or None if asset missing."""
    asset = session.query(AssetModel).filter(AssetModel.id == asset_id).first()
    if asset is None:
        return None

    common = _asset_common_fields(asset)

    if asset.status == "processing":
        from zataone.core.pipeline_progress import get as pipeline_progress_get

        return {
            "status": "processing",
            "asset_id": str(asset_id),
            "pipeline_progress": pipeline_progress_get(str(asset_id)) or {},
            **common,
        }

    if asset.status == "failed":
        return {
            "status": "failed",
            "asset_id": str(asset_id),
            "detail": "Compliance pipeline did not complete; see Cloud Run logs.",
            **common,
        }

    verdict = (
        session.query(VerdictModel)
        .filter(VerdictModel.asset_id == asset_id)
        .order_by(VerdictModel.created_at.desc())
        .first()
    )
    if verdict is None:
        return {"status": asset.status, "asset_id": str(asset_id), **common}

    result = dict(verdict.result)
    verdict_formatted = _format_verdict_response(result)
    compliance_status = verdict_formatted.pop("status", "")
    meta = verdict_formatted.get("metadata") or {}
    out = {
        "status": "completed",
        "asset_id": str(asset_id),
        "compliance_status": compliance_status,
        **common,
        **verdict_formatted,
    }
    if result.get("llm_final_review"):
        out["llm_final_review"] = result["llm_final_review"]
    if meta.get("advisory_vlm"):
        out["advisory_vlm"] = meta["advisory_vlm"]
    if meta.get("pipeline_progress"):
        out["pipeline_progress"] = meta["pipeline_progress"]
    return out


def _store_media(data: bytes | None, content_type: str) -> str | None:
    """Persist original bytes; never block ingestion on storage failure."""
    if not data:
        return None
    try:
        return ObjectStore().put(data, content_type)
    except Exception:
        logger.exception("ObjectStore put failed; continuing without stored media")
        return None


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
    external_ref: str | None = Field(
        None, max_length=255, description="Client-side reference (campaign/creative id)"
    )
    parent_asset_id: str | None = Field(
        None, description="Asset id of the previous revision (resubmission chain)"
    )


class ReviewDecisionRequest(BaseModel):
    """Request body for POST /assets/{id}/review."""

    decision: Literal["approved", "rejected", "needs_changes"]
    reviewer: str | None = Field(None, max_length=255)
    reason: str | None = Field(None, max_length=4000)
    violation_feedback: list[dict[str, Any]] | None = Field(
        None,
        description=(
            "Per-violation labels: [{violation_id, rule_id, "
            "assessment: true_positive|false_positive, note}]"
        ),
    )
    source: Literal["human_review", "appeal", "platform_feedback"] = "human_review"


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
    jurisdiction: str = "US",
) -> None:
    """Background task: run pipeline and persist result to existing asset."""
    import logging

    logger = logging.getLogger(__name__)
    try:
        pipeline = _get_pipeline(domain, jurisdiction)
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
    auth: AuthContext = Depends(get_auth_context),
    x_domain: str | None = Header(None, alias="X-Domain"),
    x_pipeline_mode: str | None = Header(None, alias="X-Pipeline-Mode"),
    x_jurisdiction: str | None = Header(None, alias="X-Jurisdiction"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """
    Run compliance check on an asset (async).

    Returns immediately with status: processing and asset_id.
    Poll GET /assets/{asset_id} for the verdict when ready.

    Optional Idempotency-Key: if provided and an asset with the same key exists,
    returns the existing verdict without re-running the pipeline.
    """
    x_tenant_id = str(auth.tenant_id) if auth.tenant_id else None
    domain = _resolve_domain(x_domain)
    jurisdiction = _JR().normalize(x_jurisdiction)
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

    storage_uri = _store_media(
        (body.content or "").encode("utf-8"), "text/plain; charset=utf-8"
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
            storage_uri=storage_uri,
            external_ref=body.external_ref,
            parent_asset_id=body.parent_asset_id,
            metadata=body.metadata,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()

    if _use_sync_pipeline():
        try:
            _get_pipeline(domain, jurisdiction).run(
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
        jurisdiction,
    )

    return {"status": "processing", "asset_id": str(asset_id), "pipeline_mode": resolve_pipeline_mode(pm), "jurisdiction": jurisdiction}


@router.post("/assets/image")
async def post_assets_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    external_ref: str | None = Form(None),
    parent_asset_id: str | None = Form(None),
    auth: AuthContext = Depends(get_auth_context),
    x_domain: str | None = Header(None, alias="X-Domain"),
    x_pipeline_mode: str | None = Header(None, alias="X-Pipeline-Mode"),
    x_jurisdiction: str | None = Header(None, alias="X-Jurisdiction"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """
    Run compliance check on an uploaded image (async).

    Returns immediately with status: processing and asset_id.
    Poll GET /assets/{asset_id} for the verdict when ready.

    Optional Idempotency-Key: if provided and an asset with the same key exists,
    returns the existing verdict without re-running the pipeline.
    """
    x_tenant_id = str(auth.tenant_id) if auth.tenant_id else None
    domain = _resolve_domain(x_domain)
    jurisdiction = _JR().normalize(x_jurisdiction)
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

    storage_uri = _store_media(image_bytes, file.content_type or "image/png")

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
            storage_uri=storage_uri,
            external_ref=external_ref,
            parent_asset_id=parent_asset_id,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()

    if _use_sync_pipeline():

        def _run_img_pipeline() -> None:
            _get_pipeline(domain, jurisdiction).run(
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
        jurisdiction,
    )

    return {"status": "processing", "asset_id": str(asset_id), "pipeline_mode": resolve_pipeline_mode(pm), "jurisdiction": jurisdiction}


@router.post("/assets/audio")
async def post_assets_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    external_ref: str | None = Form(None),
    parent_asset_id: str | None = Form(None),
    auth: AuthContext = Depends(get_auth_context),
    x_domain: str | None = Header(None, alias="X-Domain"),
    x_pipeline_mode: str | None = Header(None, alias="X-Pipeline-Mode"),
    x_jurisdiction: str | None = Header(None, alias="X-Jurisdiction"),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    """
    Run compliance check on uploaded audio: transcribe with Whisper (faster-whisper), then policy on text.

    Poll GET /assets/{asset_id} for the verdict when async; sync on Cloud Run (see _use_sync_pipeline).
    """
    x_tenant_id = str(auth.tenant_id) if auth.tenant_id else None
    domain = _resolve_domain(x_domain)
    jurisdiction = _JR().normalize(x_jurisdiction)
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

    storage_uri = _store_media(audio_bytes, file.content_type or "audio/wav")

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
            storage_uri=storage_uri,
            external_ref=external_ref,
            parent_asset_id=parent_asset_id,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()

    if _use_sync_pipeline():

        def _run_audio_pipeline() -> None:
            _get_pipeline(domain, jurisdiction).run(
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
        jurisdiction,
    )

    return {"status": "processing", "asset_id": str(asset_id), "pipeline_mode": resolve_pipeline_mode(pm), "jurisdiction": jurisdiction}


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


@router.get("/assets/{asset_id}/media")
def get_asset_media(
    asset_id: uuid.UUID = Path(..., description="Asset ID"),
) -> Response:
    """Serve the original uploaded media (image/audio/text) for review UIs."""
    session = get_session_factory()()
    try:
        asset = session.query(AssetModel).filter(AssetModel.id == asset_id).first()
        if asset is None:
            raise HTTPException(status_code=404, detail="Asset not found")
        if not asset.storage_uri:
            raise HTTPException(status_code=404, detail="No media stored for this asset")
        storage_uri = asset.storage_uri
    finally:
        session.close()

    try:
        data, content_type = ObjectStore().get(storage_uri)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="Stored media missing") from e
    return Response(content=data, media_type=content_type)


def _verdict_summary_rows(session: Any, asset_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """Latest verdict result per asset (ascending scan, last write wins)."""
    if not asset_ids:
        return {}
    rows = (
        session.query(VerdictModel)
        .filter(VerdictModel.asset_id.in_(asset_ids))
        .order_by(VerdictModel.created_at.asc())
        .all()
    )
    out: dict[uuid.UUID, dict] = {}
    for v in rows:
        out[v.asset_id] = dict(v.result) if v.result else {}
    return out


@router.get("/assets")
def list_assets(
    auth: AuthContext = Depends(get_auth_context),
    status: str | None = Query(None, description="processing | completed | failed"),
    review_state: str | None = Query(
        None,
        description="pending_review | final_approved | final_rejected | final_needs_changes | none",
    ),
    compliance_status: str | None = Query(
        None, description="COMPLIANT | REVIEW_REQUIRED | NON_COMPLIANT | LIKELY_REJECTED"
    ),
    rule_id: str | None = Query(None, description="Only assets where this rule fired"),
    external_ref: str | None = Query(None),
    parent_asset_id: uuid.UUID | None = Query(None),
    created_from: datetime | None = Query(None),
    created_to: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """List/filter assets with latest-verdict summaries (queue + dataset pulls)."""
    session = get_session_factory()()
    try:
        q = session.query(AssetModel)
        if auth.tenant_id is not None:
            q = q.filter(AssetModel.tenant_id == auth.tenant_id)
        if status:
            q = q.filter(AssetModel.status == status.strip().lower())
        if review_state:
            rs = review_state.strip().lower()
            if rs == "none":
                q = q.filter(AssetModel.review_state.is_(None))
            else:
                q = q.filter(AssetModel.review_state == rs)
        if external_ref:
            q = q.filter(AssetModel.external_ref == external_ref)
        if parent_asset_id:
            q = q.filter(AssetModel.parent_asset_id == parent_asset_id)
        if created_from:
            q = q.filter(AssetModel.created_at >= created_from)
        if created_to:
            q = q.filter(AssetModel.created_at <= created_to)
        if compliance_status:
            q = q.filter(
                session.query(VerdictModel.id)
                .filter(
                    VerdictModel.asset_id == AssetModel.id,
                    VerdictModel.status == compliance_status.strip().upper(),
                )
                .exists()
            )
        if rule_id:
            q = q.filter(
                session.query(ViolationModel.id)
                .filter(
                    ViolationModel.asset_id == AssetModel.id,
                    ViolationModel.rule_id == rule_id.strip(),
                )
                .exists()
            )

        total = q.count()
        assets = (
            q.order_by(AssetModel.created_at.desc()).offset(offset).limit(limit).all()
        )
        verdicts = _verdict_summary_rows(session, [a.id for a in assets])

        items = []
        for a in assets:
            result = verdicts.get(a.id) or {}
            items.append(
                {
                    "asset_id": str(a.id),
                    "type": a.type,
                    "status": a.status,
                    **_asset_common_fields(a),
                    "verdict": result.get("verdict"),
                    "compliance_status": result.get("status"),
                    "risk_score": result.get("risk_score"),
                    "rule_ids": sorted(
                        {
                            str(vi.get("rule_id"))
                            for vi in (result.get("violations") or [])
                            if isinstance(vi, dict) and vi.get("rule_id")
                        }
                    ),
                }
            )
        return {"items": items, "total": total, "limit": limit, "offset": offset}
    finally:
        session.close()


@router.get("/review-queue")
def get_review_queue(
    auth: AuthContext = Depends(get_auth_context),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """Assets awaiting human review, oldest first."""
    session = get_session_factory()()
    try:
        items = ReviewService().queue(
            session,
            tenant_id=auth.tenant_id,
            limit=limit,
            offset=offset,
        )
        return {"items": items, "count": len(items)}
    finally:
        session.close()


@router.post("/assets/{asset_id}/review", status_code=201)
def post_asset_review(
    body: ReviewDecisionRequest,
    asset_id: uuid.UUID = Path(..., description="Asset ID"),
    auth: AuthContext = Depends(get_auth_context),
    x_reviewer: str | None = Header(None, alias="X-Reviewer"),
) -> dict[str, Any]:
    """
    Record a human review decision; becomes the authoritative final state.

    Reviewer identity comes from the body, the X-Reviewer header, or the API key id.
    """
    reviewer = (body.reviewer or x_reviewer or "").strip()
    if not reviewer and auth.api_key_id:
        reviewer = f"api-key:{auth.api_key_id}"
    if not reviewer:
        raise HTTPException(
            status_code=400, detail="Provide reviewer in body or X-Reviewer header"
        )

    session = get_session_factory()()
    try:
        try:
            record = ReviewService().submit_decision(
                session,
                asset_id,
                reviewer=reviewer,
                decision=body.decision,
                reason=body.reason,
                violation_feedback=body.violation_feedback,
                source=body.source,
                tenant_id=auth.tenant_id,
            )
        except LookupError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        session.commit()
        out = decision_to_dict(record)
        review_state = (
            session.query(AssetModel.review_state)
            .filter(AssetModel.id == asset_id)
            .scalar()
        )
        out["review_state"] = review_state
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()

    try:
        from zataone.services.webhook_service import WebhookService

        WebhookService().fire_event_async(
            "review.completed",
            {
                "asset_id": str(asset_id),
                "decision": out["decision"],
                "review_state": out["review_state"],
                "reviewer": out["reviewer"],
            },
            tenant_id=auth.tenant_id,
        )
    except Exception:
        logger.exception("review.completed webhook dispatch failed")

    return out


@router.get("/assets/{asset_id}/reviews")
def get_asset_reviews(
    asset_id: uuid.UUID = Path(..., description="Asset ID"),
) -> dict[str, Any]:
    """All recorded review decisions for an asset (audit/history view)."""
    session = get_session_factory()()
    try:
        items = ReviewService().decisions_for_asset(session, asset_id)
        return {"items": items, "count": len(items)}
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
