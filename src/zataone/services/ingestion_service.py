# zataone asset ingestion service

from __future__ import annotations
import hashlib
import uuid
from typing import Any

from sqlalchemy.orm import Session

from zataone.models import Asset as AssetModel, Tenant, Verdict


class IngestionService:
    """Asset ingestion and normalization service."""

    def _resolve_tenant_id(self, session: Session, tenant_id: uuid.UUID | str | None) -> uuid.UUID:
        """Resolve tenant_id to UUID, using default tenant if None."""
        if tenant_id is None:
            default = session.query(Tenant).filter(Tenant.name == "default").first()
            if default is None:
                default = Tenant(name="default")
                session.add(default)
                session.flush()
            return default.id
        if isinstance(tenant_id, str):
            return uuid.UUID(tenant_id)
        return tenant_id

    def find_existing_verdict(
        self,
        session: Session,
        idempotency_key: str,
        tenant_id: uuid.UUID | str | None = None,
    ) -> tuple[uuid.UUID, dict[str, Any]] | None:
        """
        Find existing verdict by idempotency_key.

        Returns (asset_id, verdict.result dict) so callers can return asset_id to clients.
        """
        tid = self._resolve_tenant_id(session, tenant_id)
        asset = (
            session.query(AssetModel)
            .filter(
                AssetModel.idempotency_key == idempotency_key,
                AssetModel.tenant_id == tid,
            )
            .first()
        )
        if asset is None:
            return None
        verdict = (
            session.query(Verdict)
            .filter(Verdict.asset_id == asset.id)
            .order_by(Verdict.created_at.desc())
            .first()
        )
        if verdict is None:
            return None
        return asset.id, dict(verdict.result)

    def create_asset_stub(
        self,
        session: Session,
        asset: Any,
        asset_id: uuid.UUID,
        tenant_id: uuid.UUID | str | None = None,
        idempotency_key: str | None = None,
        storage_uri: str | None = None,
        external_ref: str | None = None,
        parent_asset_id: uuid.UUID | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AssetModel:
        """Create a minimal asset record with status=processing for async execution."""
        tid = self._resolve_tenant_id(session, tenant_id)
        content_hash = compute_content_hash(asset)
        asset_type = getattr(asset, "type", "image") or "image"
        if isinstance(asset_type, bytes):
            asset_type = "image"
        asset_type = str(asset_type)
        pid: uuid.UUID | None = None
        if parent_asset_id:
            try:
                pid = uuid.UUID(str(parent_asset_id))
            except ValueError:
                pid = None
        model = AssetModel(
            id=asset_id,
            tenant_id=tid,
            content_hash=content_hash,
            type=asset_type,
            status="processing",
            idempotency_key=idempotency_key,
            storage_uri=storage_uri,
            external_ref=external_ref,
            parent_asset_id=pid,
            meta=metadata or None,
        )
        session.add(model)
        session.flush()
        return model

    def persist_asset(
        self,
        session: Session,
        asset: Any,
        tenant_id: uuid.UUID | str | None = None,
        idempotency_key: str | None = None,
    ) -> AssetModel:
        """Persist an Asset. Returns the persisted Asset model."""
        tid = self._resolve_tenant_id(session, tenant_id)

        content_hash = compute_content_hash(asset)
        asset_type = getattr(asset, "type", "image") or "image"
        if isinstance(asset_type, bytes):
            asset_type = "image"
        asset_type = str(asset_type)
        asset_id_str = getattr(asset, "asset_id", None) or getattr(asset, "image_id", None)
        if asset_id_str:
            try:
                asset_id = uuid.UUID(str(asset_id_str))
            except (ValueError, TypeError):
                asset_id = uuid.uuid4()
        else:
            asset_id = uuid.uuid4()

        model = AssetModel(
            id=asset_id,
            tenant_id=tid,
            content_hash=content_hash,
            type=asset_type,
            status="completed",
            idempotency_key=idempotency_key,
        )
        session.add(model)
        session.flush()
        return model

    def set_asset_status(
        self,
        session: Session,
        asset_id: uuid.UUID,
        status: str,
    ) -> bool:
        """Update asset.status (e.g. failed). Returns True if row existed."""
        row = session.query(AssetModel).filter(AssetModel.id == asset_id).first()
        if row is None:
            return False
        row.status = status
        session.commit()
        return True


def compute_content_hash(asset: Any) -> str:
    """Compute content hash from asset (e.g. image_data, audio_data, content)."""
    content = (
        getattr(asset, "image_data", None)
        or getattr(asset, "audio_data", None)
        or getattr(asset, "content", b"")
    )
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content or b"").hexdigest()
