# zetaone asset ingestion service

import hashlib
import uuid
from typing import Any

from sqlalchemy.orm import Session

from zetaone.models import Asset as AssetModel, Tenant


class IngestionService:
    """Asset ingestion and normalization service."""

    def persist_asset(
        self,
        session: Session,
        asset: Any,
        tenant_id: uuid.UUID | str | None = None,
    ) -> AssetModel:
        """Persist an Asset. Returns the persisted Asset model."""
        tid = tenant_id
        if tid is None:
            default = session.query(Tenant).filter(Tenant.name == "default").first()
            if default is None:
                default = Tenant(name="default")
                session.add(default)
                session.flush()
            tid = default.id
        elif isinstance(tid, str):
            tid = uuid.UUID(tid)

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
        )
        session.add(model)
        session.flush()
        return model


def compute_content_hash(asset: Any) -> str:
    """Compute content hash from asset (e.g. image_data)."""
    content = getattr(asset, "image_data", None) or getattr(asset, "content", b"")
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content or b"").hexdigest()
