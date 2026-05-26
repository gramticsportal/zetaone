# zataone admin routes — tenant, API key, webhook, and audit management
#
# All endpoints require X-Admin-Secret header matching ZATAONE_ADMIN_SECRET env var.
# If ZATAONE_ADMIN_SECRET is not set, all admin endpoints return 503.

from __future__ import annotations

import csv
import io
import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from zataone.models.audit import AuditEvent
from zataone.models.tenant import Tenant
from zataone.services.api_key_service import APIKeyService
from zataone.services.webhook_service import WebhookService
from zataone.storage.database import get_session_factory

router = APIRouter(prefix="/admin", tags=["admin"])

_svc = APIKeyService()
_wh_svc = WebhookService()


def _check_admin(x_admin_secret: str | None) -> None:
    """Raise 401/503 if admin secret is missing or wrong."""
    secret = os.environ.get("ZATAONE_ADMIN_SECRET", "").strip()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin endpoints are disabled (ZATAONE_ADMIN_SECRET not configured).",
        )
    if x_admin_secret != secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin secret.",
        )


# ---------------------------------------------------------------------------
# Tenant management
# ---------------------------------------------------------------------------


class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


@router.post("/tenants", status_code=201)
def create_tenant(
    body: TenantCreateRequest,
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> dict[str, Any]:
    """Create a new tenant. Returns tenant_id to use when creating API keys."""
    _check_admin(x_admin_secret)
    session = get_session_factory()()
    try:
        tenant = Tenant(name=body.name)
        session.add(tenant)
        session.commit()
        return {"tenant_id": str(tenant.id), "name": tenant.name}
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()


@router.get("/tenants")
def list_tenants(
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> list[dict[str, Any]]:
    """List all tenants."""
    _check_admin(x_admin_secret)
    session = get_session_factory()()
    try:
        tenants = session.query(Tenant).order_by(Tenant.created_at.desc()).all()
        return [
            {
                "tenant_id": str(t.id),
                "name": t.name,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tenants
        ]
    finally:
        session.close()


# ---------------------------------------------------------------------------
# API key management
# ---------------------------------------------------------------------------


class APIKeyCreateRequest(BaseModel):
    tenant_id: str = Field(..., description="UUID of the tenant this key belongs to")
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable label")
    expires_at: datetime | None = Field(None, description="Optional expiry (ISO 8601)")


@router.post("/api-keys", status_code=201)
def create_api_key(
    body: APIKeyCreateRequest,
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> dict[str, Any]:
    """
    Create an API key for a tenant.

    Returns the raw key once — store it immediately, it cannot be retrieved again.
    """
    _check_admin(x_admin_secret)
    try:
        tenant_uuid = uuid.UUID(body.tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant_id UUID.")

    session = get_session_factory()()
    try:
        # Verify tenant exists.
        tenant = session.query(Tenant).filter(Tenant.id == tenant_uuid).first()
        if tenant is None:
            raise HTTPException(status_code=404, detail="Tenant not found.")

        raw_key, record = _svc.create_key(
            session, tenant_id=tenant_uuid, name=body.name, expires_at=body.expires_at
        )
        session.commit()
        return {
            "api_key": raw_key,
            "key_id": str(record.id),
            "prefix": record.prefix,
            "name": record.name,
            "tenant_id": str(record.tenant_id),
            "expires_at": record.expires_at.isoformat() if record.expires_at else None,
            "warning": "Store this key now — it will not be shown again.",
        }
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()


@router.get("/api-keys")
def list_api_keys(
    tenant_id: str,
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> list[dict[str, Any]]:
    """List API keys for a tenant (hashes never returned)."""
    _check_admin(x_admin_secret)
    try:
        tenant_uuid = uuid.UUID(tenant_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tenant_id UUID.")
    session = get_session_factory()()
    try:
        return _svc.list_keys(session, tenant_uuid)
    finally:
        session.close()


@router.delete("/api-keys/{key_id}", status_code=200)
def revoke_api_key(
    key_id: str,
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> dict[str, Any]:
    """Revoke an API key by ID."""
    _check_admin(x_admin_secret)
    try:
        kid = uuid.UUID(key_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid key_id UUID.")
    session = get_session_factory()()
    try:
        found = _svc.revoke_key(session, kid)
        if not found:
            raise HTTPException(status_code=404, detail="API key not found.")
        session.commit()
        return {"revoked": True, "key_id": key_id}
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Webhook management (P8)
# ---------------------------------------------------------------------------


class WebhookCreateRequest(BaseModel):
    url: str = Field(..., description="HTTPS endpoint to receive events")
    events: list[str] = Field(
        ...,
        description="Event types: verdict.completed, verdict.flagged",
    )
    tenant_id: str | None = Field(None, description="Restrict to a specific tenant (optional)")
    secret: str | None = Field(None, description="HMAC signing secret (optional)")


@router.post("/webhooks", status_code=201)
def create_webhook(
    body: WebhookCreateRequest,
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> dict[str, Any]:
    """
    Register a webhook endpoint to receive compliance events.

    Payload is signed with ``X-ZataOne-Signature: sha256=<hmac>`` when a secret
    is supplied. Supported events: ``verdict.completed``, ``verdict.flagged``.
    """
    _check_admin(x_admin_secret)
    session = get_session_factory()()
    try:
        hook = _wh_svc.register(
            session,
            url=body.url,
            events=body.events,
            tenant_id=body.tenant_id,
            secret=body.secret,
        )
        session.commit()
        return {
            "webhook_id": str(hook.id),
            "url": hook.url,
            "events": hook.events,
            "tenant_id": str(hook.tenant_id) if hook.tenant_id else None,
            "is_active": hook.is_active,
        }
    except ValueError as e:
        session.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()


@router.get("/webhooks")
def list_webhooks(
    tenant_id: str | None = Query(None),
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> list[dict[str, Any]]:
    """List active webhooks, optionally filtered by tenant."""
    _check_admin(x_admin_secret)
    session = get_session_factory()()
    try:
        return _wh_svc.list_hooks(session, tenant_id=tenant_id)
    finally:
        session.close()


@router.delete("/webhooks/{webhook_id}", status_code=200)
def delete_webhook(
    webhook_id: str,
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> dict[str, Any]:
    """Deactivate a webhook."""
    _check_admin(x_admin_secret)
    try:
        wid = uuid.UUID(webhook_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook_id UUID.")
    session = get_session_factory()()
    try:
        found = _wh_svc.deactivate(session, wid)
        if not found:
            raise HTTPException(status_code=404, detail="Webhook not found.")
        session.commit()
        return {"deactivated": True, "webhook_id": webhook_id}
    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Audit query API (P9)
# ---------------------------------------------------------------------------


def _audit_event_to_dict(ev: AuditEvent) -> dict[str, Any]:
    return {
        "id": str(ev.id),
        "asset_id": str(ev.asset_id),
        "verdict_id": str(ev.verdict_id),
        "tenant_id": str(ev.tenant_id) if ev.tenant_id else None,
        "event_type": ev.event_type,
        "action": ev.action,
        "actor": ev.actor,
        "before_state": ev.before_state,
        "after_state": ev.after_state,
        "ip_address": ev.ip_address,
        "user_agent": ev.user_agent,
        "correlation_id": str(ev.correlation_id) if ev.correlation_id else None,
        "event_metadata": ev.event_metadata,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


def _build_audit_query(
    session: Any,
    tenant_id: str | None,
    asset_id: str | None,
    event_type: str | None,
    from_date: str | None,
    to_date: str | None,
):
    """Build filtered SQLAlchemy query for audit events."""
    q = session.query(AuditEvent).order_by(AuditEvent.created_at.desc())
    if tenant_id:
        try:
            tid = uuid.UUID(tenant_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid tenant_id UUID.")
        q = q.filter(AuditEvent.tenant_id == tid)
    if asset_id:
        try:
            aid = uuid.UUID(asset_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid asset_id UUID.")
        q = q.filter(AuditEvent.asset_id == aid)
    if event_type:
        q = q.filter(AuditEvent.event_type == event_type)
    if from_date:
        try:
            q = q.filter(AuditEvent.created_at >= datetime.fromisoformat(from_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid from_date (use ISO 8601).")
    if to_date:
        try:
            q = q.filter(AuditEvent.created_at <= datetime.fromisoformat(to_date))
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid to_date (use ISO 8601).")
    return q


@router.get("/audit")
def list_audit_events(
    tenant_id: str | None = Query(None, description="Filter by tenant UUID"),
    asset_id: str | None = Query(None, description="Filter by asset UUID"),
    event_type: str | None = Query(None, description="Filter by event type, e.g. COMPLIANCE_CHECK"),
    from_date: str | None = Query(None, description="ISO 8601 start date (inclusive)"),
    to_date: str | None = Query(None, description="ISO 8601 end date (inclusive)"),
    limit: int = Query(50, ge=1, le=500, description="Max results (1–500)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> dict[str, Any]:
    """
    Query the audit log with optional filtering and pagination.

    Returns a page of audit events plus total count for the current filter.
    """
    _check_admin(x_admin_secret)
    session = get_session_factory()()
    try:
        q = _build_audit_query(session, tenant_id, asset_id, event_type, from_date, to_date)
        total = q.count()
        events = q.offset(offset).limit(limit).all()
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "events": [_audit_event_to_dict(ev) for ev in events],
        }
    finally:
        session.close()


@router.get("/audit/export")
def export_audit_events(
    format: str = Query("json", description="Export format: json or csv"),
    tenant_id: str | None = Query(None),
    asset_id: str | None = Query(None),
    event_type: str | None = Query(None),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    limit: int = Query(10000, ge=1, le=50000, description="Max rows to export"),
    x_admin_secret: str | None = Header(None, alias="X-Admin-Secret"),
) -> Response:
    """
    Export audit events as JSON or CSV.

    Use ``format=csv`` for spreadsheet-compatible output.
    Default limit is 10 000 rows; maximum 50 000.
    """
    _check_admin(x_admin_secret)
    fmt = format.lower().strip()
    if fmt not in ("json", "csv"):
        raise HTTPException(status_code=400, detail="format must be 'json' or 'csv'.")

    session = get_session_factory()()
    try:
        q = _build_audit_query(session, tenant_id, asset_id, event_type, from_date, to_date)
        events = q.limit(limit).all()
        rows = [_audit_event_to_dict(ev) for ev in events]

        if fmt == "csv":
            if not rows:
                content = ""
            else:
                buf = io.StringIO()
                writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                for row in rows:
                    # Flatten JSON columns to strings for CSV
                    flat = {
                        k: (str(v) if isinstance(v, (dict, list)) else v)
                        for k, v in row.items()
                    }
                    writer.writerow(flat)
                content = buf.getvalue()
            return Response(
                content=content,
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=audit_export.csv"},
            )

        import json as _json
        return Response(
            content=_json.dumps(rows, default=str),
            media_type="application/json",
        )
    finally:
        session.close()
