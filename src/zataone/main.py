# zataone FastAPI application entry point

from __future__ import annotations
import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from zataone.api.admin import router as admin_router
from zataone.api.routes import router as api_router

# Repo `web/` (Docker: /app/web). ZATAONE_WEB_DIR overrides editable-install path drift.
_WEB_DIR = Path(
    os.environ.get("ZATAONE_WEB_DIR", "")
).resolve() if os.environ.get("ZATAONE_WEB_DIR", "").strip() else (
    Path(__file__).resolve().parent.parent.parent / "web"
)

app = FastAPI(
    title="zataone",
    description="AI Compliance Platform — Deterministic, evidence-first architecture",
    version="0.1.0",
)

# Browser uploads from a separate origin (static site / local HTML) need CORS.
# Production: CORS_ORIGINS=https://app.example.com,https://www.example.com
# Dev-only escape hatch: CORS_ALLOW_ALL=true (do not use in production)
_origins_env = os.environ.get("CORS_ORIGINS", "").strip()
if os.environ.get("CORS_ALLOW_ALL", "").lower() in ("1", "true", "yes"):
    _cors_origins = ["*"]
    _cors_credentials = False
elif _origins_env:
    _cors_credentials = True
    _cors_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
else:
    _cors_credentials = True
    _cors_origins = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _no_cache_ui_html(request: Request, call_next):
    """Avoid stale /ui/*.html after deploy (Safari especially caches static HTML)."""
    response = await call_next(request)
    p = request.url.path
    if p.startswith("/ui/") and (p.endswith(".html") or p.endswith(".htm")):
        response.headers["Cache-Control"] = "no-store, max-age=0, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


app.include_router(api_router)                          # legacy: /assets
app.include_router(api_router, prefix="/api/v1")        # versioned: /api/v1/assets
app.include_router(admin_router)


@app.on_event("startup")
def _start_reaper() -> None:
    """Sweep assets stuck in 'processing' (instance recycles kill bg threads)."""
    from zataone.core.reaper import start_reaper

    start_reaper()

if _WEB_DIR.is_dir():
    app.mount(
        "/ui",
        StaticFiles(directory=str(_WEB_DIR), html=True),
        name="ui",
    )


@app.get("/")
def root() -> dict[str, str]:
    """Base URL — Cloud Run root otherwise returns 404."""
    out: dict[str, str] = {
        "service": "zataone",
        "docs": "/docs",
        "health": "/health",
    }
    if _WEB_DIR.is_dir():
        out["ui"] = "/ui/policylens.html"
        out["review_ui"] = "/ui/reviewlens.html"
    return out


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "zataone"}


@app.get("/health/ui-asset")
def health_ui_asset() -> dict[str, Any]:
    """Debug: which policylens.html the server reads (bytes + path)."""
    p = _WEB_DIR / "policylens.html"
    exists = p.is_file()
    size = p.stat().st_size if exists else 0
    has_pipeline_mode = False
    if exists and size < 500_000:
        try:
            has_pipeline_mode = "pipelineModeRow" in p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    return {
        "web_dir": str(_WEB_DIR),
        "policylens_path": str(p),
        "exists": exists,
        "bytes": size,
        "has_pipeline_mode_ui": has_pipeline_mode,
    }
