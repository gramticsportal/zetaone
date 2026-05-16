# ZataOne

**Deterministic, evidence-first AI compliance platform for enterprise regulatory enforcement.**

ZataOne provides a scalable architecture for validating content against configurable policies—from single-domain checks to global multi-modal compliance. AI models act as sensors that extract signals; policies make deterministic, auditable decisions.

---

## Overview

ZataOne is designed for organizations that need:

- **Legally defensible decisions** — Deterministic evaluation with complete audit trails
- **Evidence-first design** — Every violation links to traceable source content
- **Configuration-driven growth** — Add domains, modalities, and jurisdictions without core rewrites
- **Multi-tenant readiness** — Built for SaaS deployment with tenant isolation

The platform follows a strict separation of concerns: AI extracts signals, the policy engine evaluates rules, and the evidence system produces human-reviewable proof.

---

## Architecture

```
Asset → Normalization → Signal Extraction → Document Build → Policy Retrieval (optional)
     → Policy Evaluation → Evidence → Verdict → Audit
```

| Layer | Responsibility |
|-------|-----------------|
| **Asset Ingestion** | Multi-protocol intake, format normalization, content chunking |
| **Signal Extraction** | Pluggable extractors (text, image, video) produce machine-readable facts |
| **Policy Engine** | Deterministic rule evaluation against signals |
| **Evidence** | Traceable, immutable proof with anchors to source content |
| **Verdict** | Final decision with risk scoring and explainability |
| **Audit** | Immutable trail for regulatory and operational transparency |

**Core principle:** AI models are sensors—they extract signals but never make enforcement decisions. Policies are configuration-driven and versioned for auditability.

---

## Deterministic Pipeline

1. **Asset** — Content ingested and normalized to an internal representation
2. **Signal** — Extractors produce structured facts (entities, claims, metadata)
3. **Policy** — Rules evaluate signals; same inputs always yield same outputs
4. **Evidence** — Violations generate anchored, tamper-proof evidence bundles
5. **Verdict** — Compliant / non-compliant / needs-review with risk score
6. **Audit** — Every decision recorded for compliance and debugging

Expansion is configuration-only:

- **Policy packs** — New domains (healthcare, finance, advertising) via YAML/config
- **Signal extractors** — New modalities (text, image, video) as pluggable modules
- **Jurisdiction adapters** — New regulations via policy overrides

---

## Policy engine enhancements

Recent work extends the deterministic core without changing the verdict contract:

| Capability | Description | Default |
|------------|-------------|---------|
| **Document layer** | Merges OCR, ASR, and vision scene text into `normalized_text` for explainability and optional rule matching | Built every run; matching uses document text only when flag is on |
| **Policy corpus** | Versioned `policy_pack` + `clauses` in YAML (`meta_ads.yaml`); registry in `configs/policy_registry.yaml` | Loaded for `ad_compliance` |
| **BM25 retrieval** | Shortlists active rule IDs from document text before evaluation | Off |
| **DSL pilot** | Explicit `match:` blocks (`any` / `terms` / `requires_context` / `exceptions`) for selected Meta rules | Mixed with legacy keyword rules |

**Feature flags** (environment variables):

| Variable | Purpose | Default |
|----------|---------|---------|
| `ZATAONE_DOCUMENT_CENTRIC` | Match rules against unified document text instead of per-signal fragments | `false` |
| `ZATAONE_POLICY_RETRIEVAL` | Enable BM25 rule shortlist | `false` |
| `ZATAONE_RETRIEVAL_TOP_K` | Max rules retrieved | `8` |
| `ZATAONE_RETRIEVAL_FALLBACK_ALL` | If retrieval returns nothing, evaluate all rules | `true` |

Verdict and graph metadata may include `document`, `policy_pack`, `retrieval`, and the flag states above for UI explainability.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | Python 3.11+, FastAPI |
| **Database** | PostgreSQL, SQLAlchemy, Alembic |
| **Config** | YAML, python-dotenv |
| **Logging** | Loguru |
| **Packaging** | setuptools, pyproject.toml (PEP 621) |

---

## Local Development

### Prerequisites

- Python 3.11+
- pip

### Setup

```bash
# Clone the repository
git clone https://github.com/Salmanportal/ZetaOna.git
cd ZetaOna

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in editable mode
pip install -e .

# Run the API
uvicorn zataone.main:app --reload --port 8000
```

### Verify

```bash
curl http://localhost:8000/health
# {"status":"ok","service":"zataone"}
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/assets` | Submit asset for compliance check (async) |
| POST | `/assets/image` | Submit image for compliance check (async) |
| POST | `/assets/audio` | Submit audio for transcription (faster-whisper) + compliance check |
| GET | `/assets/{asset_id}` | Poll for verdict when ready |
| GET | `/assets/{asset_id}/graph` | Compliance graph: signals, evidence, violations, verdict, plus `document`, `policy_pack`, `retrieval` when available |
| POST | `/assets/{asset_id}/llm-final-review` | Optional advisory pass (Gemini VLM + text); does not override deterministic verdict |

**POST /assets** — Submit content for compliance evaluation. Returns immediately with `status: processing` and `asset_id`. Poll `GET /assets/{asset_id}` for the verdict.

Optional headers:
- `X-Tenant-ID` — Tenant ID for multi-tenant isolation
- `Idempotency-Key` — If provided and an asset with the same key exists, returns the existing verdict without re-running the pipeline

Request body:

```json
{
  "content": "string (required)",
  "type": "text|image|video|audio (required)",
  "asset_id": "string (optional)",
  "metadata": "object (optional)"
}
```

Immediate response:

```json
{
  "status": "processing",
  "asset_id": "uuid"
}
```

**GET /assets/{asset_id}** — Poll for result. Returns `status: processing` while running, or `status: completed` with verdict when done:

```json
{
  "status": "completed",
  "asset_id": "uuid",
  "verdict": "likely_approved | borderline | likely_rejected",
  "risk_score": 0.0,
  "compliance_status": "COMPLIANT | REVIEW_REQUIRED | NON_COMPLIANT",
  "violations": [],
  "signals": [],
  "fix_suggestions": [],
  "metadata": {}
}
```

Example:

```bash
# Submit
RESP=$(curl -s -X POST http://localhost:8000/assets \
  -H "Content-Type: application/json" \
  -d '{"content": "Guaranteed instant cure", "type": "text"}')
ASSET_ID=$(echo $RESP | jq -r '.asset_id')

# Poll for result
curl "http://localhost:8000/assets/$ASSET_ID"
```

### Advisory review (optional Gemini)

After the pipeline **completes**, you can request an **advisory** second read that uses **Google Gemini** (not the policy engine). It **does not** change the binding compliance outcome; the result is stored on the latest verdict (e.g. `llm_final_review`) for explainability.

- **Text:** One Gemini call with structured context (deterministic verdict, signals, violations).
- **Image:** If the asset is an image, **re-upload the same file** in the multipart `file` field so the service can run a **VLM** pass first (compliance-oriented visual inspection), then merge that into the JSON context for the final text call.

| Variable | Role |
|----------|------|
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Required for advisory calls (Google AI / AI Studio) |
| `ZATAONE_LLM_FINAL_REVIEW` | `0`/`false` to disable; if unset, advisory is on when a Gemini key is set |
| `GEMINI_MODEL` | Default generative model (text + vision if unset; see [Gemini API models](https://ai.google.dev/gemini-api/docs/models)) |
| `GEMINI_REVIEW_MODEL` / `GEMINI_VLM_MODEL` | Optional overrides for the text and vision steps |
| `GEMINI_REVIEW_MAX_TOKENS` / `GEMINI_VLM_MAX_TOKENS` | Cap advisory JSON / VLM inspection length (defaults are set in code) |
| `ZATAONE_ALLOWED_DOMAINS` | Comma-separated; requests send **`X-Domain`**; unknown domains return **403** |

### Compliance graph (`GET /assets/{asset_id}/graph`)

Used by PolicyLens and other explainability clients. Typical top-level fields:

| Field | Description |
|-------|-------------|
| `signals` | Extractor output (OCR, vision, embedding, ASR, VLM, etc.) |
| `violations` | Rule hits with severity |
| `evidence` | Rows linked to violations (text spans, bboxes) |
| `verdict` | Final deterministic outcome |
| `document` | `normalized_text`, modality, span metadata (when pipeline built a document) |
| `policy_pack` | Pack id, platform, jurisdiction, version |
| `retrieval` | `method` (`bm25` or `all_rules`), `retrieved_rule_ids`, `retrieval_scores` |
| `document_centric_enabled` / `policy_retrieval_enabled` | Echo of server flags |

### PolicyLens UI

**[web/policylens.html](web/policylens.html)** — static demo UI for production-style reviews (no separate frontend build).

| Area | Features |
|------|----------|
| **Run flow** | Image or text upload → poll → graph; 6-step pipeline progress; run stats (time, signal count, rules in scope) |
| **Verdict** | Polished card: compliance status (green/yellow/red), platform verdict, risk score, violation count |
| **Explainability** | Collapsible panels: normalized document with highlighted spans, policy pack/version, BM25 retrieved rules + scores, triggered rules, signals grouped by modality (confidence bars, extractor IDs), raw JSON |
| **Overlays** | OCR / vision bboxes from graph; violation-scoped or all-signal mode |
| **Advisory** | Optional Gemini pass via `POST /assets/{id}/llm-final-review` (does not override verdict) |

Configure **API base URL** and **`X-Domain`** in the page; enable **CORS** on the API (`CORS_ORIGINS` or `CORS_ALLOW_ALL` for local testing).

```bash
# API + UI (same origin when using uvicorn static mount)
uvicorn zataone.main:app --reload --port 8000
# Open http://localhost:8000/ui/policylens.html

# Or serve web/ separately (set API base URL in the page)
cd web && python -m http.server 5500
# Open http://localhost:5500/policylens.html
```

See [web/README.md](web/README.md). Legacy [web/sentrilens.html](web/sentrilens.html) redirects to PolicyLens.

---

## Database & Persistence

The pipeline persists the full compliance graph to PostgreSQL when `persist=True` (default):

- **assets** — Ingested content with content hash and type
- **signals** — Extracted features from each extractor
- **evidence** — Violation evidence linked to signals
- **verdicts** — Final decision with risk score and result
- **audit_events** — Immutable trail for each compliance check

Set `DATABASE_URL` before running (default: `postgresql://localhost:5432/zataone`):

```bash
export DATABASE_URL=postgresql://zataone:zataone@127.0.0.1:5432/zataone
```

Create tables:

```bash
python -c "from zataone.storage.database import create_all_tables; create_all_tables(); print('OK')"
```

**Upgrading existing DB** — To add idempotency and async status support:

```bash
psql $DATABASE_URL -f migrations/add_idempotency_key.sql
psql $DATABASE_URL -f migrations/add_asset_status.sql
```

PostgreSQL via Docker:

```bash
docker run --name zataone-postgres \
  -e POSTGRES_DB=zataone \
  -e POSTGRES_USER=zataone \
  -e POSTGRES_PASSWORD=zataone \
  -p 5433:5432 -d postgres:15

export DATABASE_URL=postgresql://zataone:zataone@127.0.0.1:5433/zataone
```

---

## Tests

```bash
pytest tests/ -v
```

**Full local check** (Docker Postgres + schema + migrations + pytest). Start Docker Desktop, then:

```bash
./scripts/run_local_check.sh
```

- `tests/test_zataone_pipeline.py` — Mocked pipeline (no external deps)
- `tests/test_persistence.py` — Integration test for DB persistence (requires PostgreSQL)
- `tests/test_document_builder.py`, `tests/test_document_regression.py` — Document normalization and aggregation
- `tests/test_policy_engine_document_centric.py` — Document-centric vs fragment matching
- `tests/test_policy_pack_loader.py` — Policy corpus / pack loading
- `tests/test_policy_retrieval.py` — BM25 shortlist behavior
- `tests/test_dsl_evaluator.py`, `tests/test_policy_engine_dsl_pilot.py` — DSL match evaluation
- `tests/test_explainability_document.py` — Graph API document metadata

---

## Configuration

| Path | Purpose |
|------|---------|
| `configs/policy_registry.yaml` | Maps domains to policy pack paths |
| `src/zataone/domains/ad_compliance/policies/meta_ads.yaml` | Meta Ads pack: `policy_pack`, `clauses`, `rules` (legacy + DSL `match:` pilot) |
| `configs/logging.yaml` | Loguru / logging config |

---

## Docker Instructions

### Build and run

```bash
# From project root
docker compose -f docker/docker-compose.yml up --build
```

The API is available at `http://localhost:8000`. Source code is mounted for development; changes are reflected on reload.

### Project name

The Compose project name is `zataone`. Override if needed:

```bash
docker compose -p zataone -f docker/docker-compose.yml up
```

### Deploy to Google Cloud

Step-by-step: **[docs/deploy-gcp-step-by-step.md](docs/deploy-gcp-step-by-step.md)** (project setup → Cloud SQL → Cloud Run → static `web/` UI).

**Image build (`cloudbuild.yaml` + `docker/Dockerfile`):**

- **Hugging Face models** (Grounding DINO + SigLIP) are **pre-downloaded during the Docker build** via `docker/preload_models.py` into `/app/.cache/huggingface`, so Cloud Run does not re-fetch full weights on every cold start.
- **Cloud Build** uses a larger worker (`options.machineType`, e.g. `E2_HIGHCPU_32`) so the preload step has enough RAM.
- Optional Hub auth (higher rate limits during build): pass **`_HF_TOKEN`** in substitutions (see `cloudbuild.yaml`).

**Rebuild and roll out a new image** (run from repo root; deploy only runs if the build succeeds):

```bash
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
# Optional: export HF_TOKEN=hf_...

gcloud builds submit --config cloudbuild.yaml \
  --substitutions=_REGION="${REGION}",_HF_TOKEN="${HF_TOKEN:-}" . \
  && gcloud run services update zataone-api \
    --project="${PROJECT_ID}" \
    --region="${REGION}" \
    --image="${REGION}-docker.pkg.dev/${PROJECT_ID}/zataone/zataone-api:latest"
```

**Runtime notes:** Set **`DATABASE_URL`** to the Cloud SQL Unix socket form, attach the instance on the service, set **`CORS_ORIGINS`** for your UI origin, and **`HF_TOKEN`** on Cloud Run if you still want Hub access for edge cases. The Dockerfile sets **`ZATAONE_DISABLE_CORE_STUB_EXTRACTORS=true`** so domain extractors are used on Cloud Run.

**Web UI:** `web/policylens.html` (**PolicyLens**) is served at **`/ui/policylens.html`**. Set **`GEMINI_*`** and **`CORS_ORIGINS`** on the Cloud Run service for advisory review from the browser (see *Advisory review* above). **`/ui/sentrilens.html`** redirects to PolicyLens.

---

## Future Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **Foundation** | PostgreSQL, ingestion API, extractors, policy engine, PolicyLens UI | In progress |
| **Explainability** | Document layer, policy corpus, BM25 retrieval, DSL pilot, graph metadata | Shipped (flags default off) |
| **MVP** | Additional policy packs, hardened auth, audit exports | Planned |
| **Scale** | Multi-tenancy, webhooks, video pipeline, 10+ packs | Planned |
| **Platform** | Policy builder UI, extractor SDK, marketplace, SOC 2 | Planned |

---

## License

See [LICENSE](LICENSE) for details.
