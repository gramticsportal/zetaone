# zetaone API routes

from types import SimpleNamespace
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from zetaone.core.pipeline import CompliancePipeline

router = APIRouter()


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


@router.post("/assets")
def post_assets(body: AssetCreateRequest) -> dict[str, Any]:
    """
    Run compliance check on an asset.

    Returns verdict, risk_score, status, violations, signals, fix_suggestions, metadata.
    """
    asset = SimpleNamespace(
        asset_id=body.asset_id,
        content=body.content,
        type=body.type,
        metadata=body.metadata or {},
    )

    try:
        pipeline = CompliancePipeline(domain="ad_compliance")
        result = pipeline.run(asset, persist=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return {
        "verdict": result.get("verdict", ""),
        "risk_score": result.get("risk_score", 0.0),
        "status": result.get("status", ""),
        "violations": result.get("violations", []),
        "signals": result.get("signals", []),
        "fix_suggestions": result.get("fix_suggestions", []),
        "metadata": result.get("metadata", {}),
    }
