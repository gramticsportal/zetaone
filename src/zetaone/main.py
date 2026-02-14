# zetaone FastAPI application entry point

from fastapi import FastAPI

from zetaone.api.routes import router as api_router

app = FastAPI(
    title="zetaone",
    description="AI Compliance Platform — Deterministic, evidence-first architecture",
    version="0.1.0",
)

app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "service": "zetaone"}
