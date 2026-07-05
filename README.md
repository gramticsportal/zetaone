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

The platform follows a strict separation of concerns: AI extracts signals, the policy engine evaluates rules, and the evidence system produces human-reviewable proof. Borderline and flagged outcomes flow into a **human review queue** (ReviewLens); recorded decisions are authoritative and double as labeled data for rule tuning.

---

## Compliance ontology corpus

Structured ad-compliance knowledge base: every **platform** (Meta, Google, TikTok, …) and **regulator** (FTC, FDA, SEC, …) policy maps into one shared schema — cross-source canonical rules, labeled evals, and verified enforcement precedents.

```mermaid
flowchart TB
  subgraph sources["25 sources"]
    P["12 ad platforms<br/>Meta · Google · TikTok · …"]
    R["13 regulators<br/>FTC · FDA · SEC · …"]
  end

  subgraph policy["Policy layer"]
    C["157 clauses · 11 categories"]
    Ru["128 rules"]
  end

  subgraph unify["Unification"]
    CR["52 canonical rules"]
    M["37 cross-source mappings"]
  end

  subgraph learn["Learning & proof"]
    E["614 eval examples<br/>570 seed + 44 precedent"]
    PR["128 verified precedents"]
  end

  subgraph check["Quality"]
    V["validate.py"]
    B["benchmark · 21/21 retrieval tests"]
  end

  P --> C
  R --> C
  C --> Ru --> CR
  CR --> M
  CR --> E
  CR --> PR
  C --> V
  E --> B
  PR --> B
```

**Flow:** policies → clauses & rules → canonical rules → mappings, evals, precedents → validation & benchmarks.

Docs: [`ontology/README.md`](ontology/README.md) · full architecture map [`ontology/ONTOLOGY_MAP.md`](ontology/ONTOLOGY_MAP.md)

---

## Architecture

### System schematic

How clients, the API, pipeline, storage, and optional advisory layer connect:

```mermaid
flowchart TB
  subgraph clients["Clients"]
    PL["PolicyLens UI<br/>web/policylens.html"]
    RL["ReviewLens UI<br/>web/reviewlens.html"]
    EXT["Static host<br/>e.g. underintelligence.com"]
    API_CLIENT["curl / integrations"]
  end

  subgraph gcp["Google Cloud — zetaone-493600"]
    CR["Cloud Run<br/>zataone-api"]
    AR["Artifact Registry<br/>Docker image"]
    SQL["Cloud SQL<br/>PostgreSQL"]
    CB["Cloud Build<br/>cloudbuild.yaml"]
  end

  subgraph api["FastAPI — zataone.main"]
    ROUTES["API routes<br/>/assets · /graph · /review-queue · /health"]
    CORS["CORS + X-Domain"]
    REV["ReviewService<br/>queue + decisions + labels"]
    REAP["Reaper<br/>stuck-asset sweep"]
  end

  subgraph pipeline["CompliancePipeline"]
    ING["IngestionService"]
    REG["ExtractorRegistry"]
    DOC["DocumentBuilder"]
    RET["PolicyRetriever<br/>BM25 optional"]
    PE["PolicyEngine<br/>YAML + DSL"]
    EV["EvidenceService"]
    VS["VerdictService"]
    AUD["AuditService"]
  end

  subgraph extractors["Domain extractors — ad_compliance"]
    OCR["OCR"]
    VIS["Vision<br/>Grounding DINO"]
    EMB["Embedding<br/>SigLIP"]
    ASR["ASR<br/>faster-whisper"]
    VLM["VLM"]
    TXT["Text"]
  end

  subgraph config["Configuration"]
    YAML["meta_ads.yaml<br/>policy_pack · clauses · rules"]
    REGISTRY["policy_registry.yaml"]
    FLAGS["Feature flags<br/>DOCUMENT_CENTRIC · POLICY_RETRIEVAL"]
  end

  subgraph advisory["Optional — non-binding"]
    GEM["Gemini advisory<br/>llm-final-review"]
  end

  subgraph persist["Persistence"]
    PG[("PostgreSQL")]
    TBL["assets · signals · violations<br/>evidence · verdicts · review_decisions<br/>audit_events"]
    OBJ["ObjectStore<br/>original media (disk / GCS)"]
  end

  PL -->|"HTTPS + API base URL"| CR
  RL -->|"/review-queue · /assets/{id}/review"| CR
  EXT -->|"HTTPS + CORS_ORIGINS"| CR
  API_CLIENT --> CR
  CB --> AR --> CR
  CR --> ROUTES
  ROUTES --> CORS
  CORS --> ING
  ING --> REG
  REG --> OCR & VIS & EMB & ASR & VLM & TXT
  OCR & VIS & EMB & ASR & VLM & TXT --> DOC
  YAML & REGISTRY --> PE
  FLAGS --> DOC & RET & PE
  DOC --> RET --> PE
  PE --> EV --> VS --> AUD
  VS --> ROUTES
  AUD --> PG
  ING --> PG
  ING --> OBJ
  ROUTES --> REV --> PG
  REAP --> PG
  PG --> TBL
  CR --- SQL
  ROUTES -.->|"POST /assets/{id}/llm-final-review"| GEM
  GEM -.-> VS

  ROUTES -->|"GET /assets/{id}/graph"| PL
```

> Diagrams render on GitHub. For a local preview, use VS Code with a Mermaid extension or [mermaid.live](https://mermaid.live).

### Request flow (one compliance check)

```mermaid
sequenceDiagram
  autonumber
  participant U as User / PolicyLens
  participant API as FastAPI
  participant P as CompliancePipeline
  participant X as Extractors
  participant D as DocumentBuilder
  participant R as PolicyRetriever
  participant E as PolicyEngine
  participant DB as PostgreSQL

  U->>API: POST /assets or /assets/image
  API->>DB: create asset stub (processing)
  API-->>U: asset_id + status processing
  API->>P: run pipeline (sync or background)

  P->>X: extract per modality
  X-->>P: signals[]
  P->>D: build normalized document
  opt ZATAONE_POLICY_RETRIEVAL=true
    P->>R: BM25 shortlist rule IDs
    R-->>P: retrieved_rule_ids + scores
  end
  P->>E: evaluate rules (+ optional document text)
  E-->>P: violations[]
  P->>P: evidence + verdict + metadata
  P->>DB: persist graph (atomic)
  P-->>API: verdict

  U->>API: GET /assets/{id} (poll)
  API-->>U: status completed + verdict
  U->>API: GET /assets/{id}/graph
  API-->>U: signals, evidence, document, policy_pack, retrieval

  opt Advisory only
    U->>API: POST /assets/{id}/llm-final-review
    API-->>U: Gemini narrative (does not change verdict)
  end

  opt Human review (borderline / flagged / degraded)
    U->>API: GET /review-queue
    API-->>U: assets with review_state pending_review
    U->>API: GET /assets/{id}/media
    API-->>U: original creative (ObjectStore)
    U->>API: POST /assets/{id}/review (decision + per-violation labels)
    API->>DB: review_decisions + review_state final_* + audit event
    API-->>U: recorded decision (authoritative)
  end
```

### Pipeline stages (deterministic core)

```mermaid
flowchart LR
  A[Asset] --> B[Signal extraction]
  B --> C[Document build]
  C --> D{Retrieval enabled?}
  D -->|yes| E[BM25 rule shortlist]
  D -->|no| F[All rules]
  E --> G[Policy evaluation]
  F --> G
  G --> H[Evidence]
  H --> I[Verdict + risk score]
  I --> I2{Extractor failure?}
  I2 -->|yes| I3[Cap at REVIEW_REQUIRED<br/>degraded_extractors]
  I2 -->|no| J
  I3 --> J[Audit + DB persist<br/>+ review_state]
  J --> K[Graph API / PolicyLens]
  J --> L[Review queue / ReviewLens]
  L --> M[Human decision<br/>recorded as labels]
```

| Layer | Responsibility |
|-------|-----------------|
| **Asset Ingestion** | Multi-protocol intake, format normalization, content chunking |
| **Signal Extraction** | Pluggable extractors (text, image, video) produce machine-readable facts |
| **Policy Engine** | Deterministic rule evaluation against signals |
| **Evidence** | Traceable, immutable proof with anchors to source content |
| **Verdict** | Final decision with risk scoring and explainability |
| **Human Review** | Borderline, flagged, and degraded outcomes queue for a recorded human decision (`review_decisions`); per-violation true/false-positive labels feed rule tuning |
| **Audit** | Immutable trail for regulatory and operational transparency |

**Core principle:** AI models are sensors—they extract signals but never make enforcement decisions. Policies are configuration-driven and versioned for auditability.

---

## Deterministic Pipeline

1. **Asset** — Content ingested and normalized to an internal representation
2. **Signal** — Extractors produce structured facts (entities, claims, metadata)
3. **Policy** — Rules evaluate signals; same inputs always yield same outputs
4. **Evidence** — Violations generate anchored, tamper-proof evidence bundles
5. **Verdict** — Compliant / non-compliant / needs-review with risk score; extractor failures cap the verdict at needs-review (fail-to-review, never silent approval)
6. **Review** — Borderline / flagged / degraded assets enter `review_state: pending_review`; a recorded human decision (ReviewLens or API) becomes the authoritative final state
7. **Audit** — Every decision recorded for compliance and debugging

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

### Pipeline modes (Quick vs Full)

Clients select mode with header **`X-Pipeline-Mode: full`** (default) or **`fast`**, or env **`ZATAONE_PIPELINE_MODE`**.

| Mode | Extractors | YAML rule engine | Gemini | Display authority |
|------|------------|------------------|--------|-------------------|
| **Quick (`fast`)** | Skipped | Off | **One** vision+policy call by default (`ZATAONE_FAST_COMBINED_REVIEW=true`), else VLM then text LLM | **LLM vs `policy_context`** (`verdict_authority: advisory`) |
| **Full (`full`)** | OCR / vision / etc. | **Off by default** (`ZATAONE_POLICY_ENGINE_ENABLED=false`); optional audit path when `true` | VLM ∥ core, then text LLM vs signals + VLM + policy | **LLM** when engine off; **rule engine + optional LLM second read** when engine on |

**Quick** is for fast demos (e.g. handwriting where OCR returns 0 signals). **Full** keeps extractor signals and graph overlays for explainability; the LLM compares signals + VLM to the policy corpus unless the YAML engine is enabled.

Additional flags:

| Variable | Purpose | Default |
|----------|---------|---------|
| `ZATAONE_POLICY_ENGINE_ENABLED` | Run YAML `policy_engine.evaluate()` on Full | `false` |
| `ZATAONE_FAST_COMBINED_REVIEW` | Quick images: single Gemini pass (vision + policy JSON) | `true` |
| `ZATAONE_FAST_COMBINED_MAX_TOKENS` | Cap combined Quick response size | `1024` |
| `ZATAONE_PIPELINE_ADVISORY` | Auto-run Gemini at end of pipeline | on when `GEMINI_API_KEY` set |

API responses include `pipeline_mode`, `verdict_authority`, `policy_engine_ran`, `display_compliance_status`, and `deterministic_compliance_status` (when applicable).

**Hybrid verdict model:** Quick and Full (engine off) use **LLM vs policy** for display. When `ZATAONE_POLICY_ENGINE_ENABLED=true`, the YAML engine is the audit authority and the LLM **explains / augments** (escalates on 0 signals or diverges).

### Platform additions (merged)

| Area | Notes |
|------|--------|
| **API keys** | `src/zataone/api/auth.py`, admin routes; migration `create_api_keys_table.sql` |
| **Webhooks** | `webhook_service.py`; migration `create_webhooks_table.sql` |
| **Jurisdiction** | `JurisdictionRouter` — US / EU / UK policy packs (`meta_ads_eu.yaml`, `meta_ads_uk.yaml`) |
| **Text / video** | Expanded `TextExtractor`; `VideoExtractor` for video assets |
| **Local smoke test** | `test_local.py` at repo root |

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
| GET | `/assets` | List/filter assets: `status`, `review_state`, `compliance_status`, `rule_id`, `external_ref`, `parent_asset_id`, date range, pagination |
| GET | `/assets/{asset_id}` | Poll for verdict when ready |
| GET | `/assets/{asset_id}/media` | Serve the original uploaded media from the ObjectStore (used by ReviewLens) |
| GET | `/assets/{asset_id}/graph` | Compliance graph: signals, evidence, violations, verdict, plus `document`, `policy_pack`, `retrieval` when available |
| POST | `/assets/{asset_id}/llm-final-review` | Optional advisory pass (Gemini VLM + text); does not override deterministic verdict |
| GET | `/review-queue` | Assets awaiting human review (`review_state: pending_review`), oldest first |
| POST | `/assets/{asset_id}/review` | Record a human decision (`approved` / `rejected` / `needs_changes`) with reason + per-violation true/false-positive labels; authoritative, fires `review.completed` webhook |
| GET | `/assets/{asset_id}/reviews` | Decision history for an asset |

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
  "metadata": "object (optional)",
  "external_ref": "string (optional — client campaign/creative id)",
  "parent_asset_id": "uuid (optional — previous revision, builds resubmission chains)"
}
```

`external_ref` and `parent_asset_id` are also accepted as multipart form fields on `/assets/image` and `/assets/audio`. Original bytes are stored content-addressed in the ObjectStore and served back via `GET /assets/{id}/media`.

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

### Advisory review (Gemini)

When **`ZATAONE_PIPELINE_ADVISORY`** is enabled (default if `GEMINI_API_KEY` is set), the pipeline runs Gemini automatically at the end of each check.

- **Quick:** Primary assessment — image + compact `policy_context` (clauses/rules) → JSON with `recommended_compliance_status` / `recommended_verdict`.
- **Full (engine off):** Same primary role using **signals + VLM + policy_context**.
- **Full (engine on):** Second read only — does not replace YAML rule outcomes; use `agreement_with_deterministic`.

Manual re-run: **`POST /assets/{asset_id}/llm-final-review`** (PolicyLens button). For images, re-upload the file in multipart **`file`** if VLM must run again.

| Variable | Role |
|----------|------|
| `GEMINI_API_KEY` or `GOOGLE_API_KEY` | Required for advisory calls (Google AI / AI Studio) |
| `ZATAONE_LLM_FINAL_REVIEW` | `0`/`false` to disable; if unset, advisory is on when a Gemini key is set |
| `GEMINI_FAST_MODEL` / `GEMINI_MODEL` | Model for Quick combined pass and text review |
| `GEMINI_REVIEW_MODEL` / `GEMINI_VLM_MODEL` | Optional overrides for Full text and vision steps |
| `GEMINI_REVIEW_MAX_TOKENS` / `GEMINI_VLM_MAX_TOKENS` | Cap advisory JSON / VLM inspection length |
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
| **Pipeline toggle** | **Full** (extractors + LLM vs policy) or **Quick** (VLM → LLM vs policy; optional single Gemini pass on API) |
| **Run flow** | Image or text upload → poll (or sync on Cloud Run) → graph; mode-specific progress bar (4 or 6 steps) |
| **Verdict** | **LLM + policy** card when `verdict_authority: advisory`; dual audit/display cards when YAML engine ran |
| **Explainability** | Collapsible panels: document, policy pack, BM25 rules, signals, raw JSON |
| **Overlays** | OCR / vision bboxes (Full only; Quick skips extractors) |
| **Advisory** | Inline pipeline Gemini + re-run via `POST /assets/{id}/llm-final-review` |

**Production:** API at **`/ui/policylens.html`** (same origin) or static host (e.g. underintelligence.com) with **`CORS_ORIGINS`**. Artifact Registry image path uses repo **`zataone`** (not `zetaone`). Cloud Run service: **`zataone-api`**.

Configure **API base URL** and **`X-Domain`** in the page; enable **CORS** on the API (`CORS_ORIGINS` or `CORS_ALLOW_ALL` for local testing).

```bash
# API + UI (same origin when using uvicorn static mount)
uvicorn zataone.main:app --reload --port 8000
# Open http://localhost:8000/ui/policylens.html

# Or serve web/ separately (set API base URL in the page)
cd web && python -m http.server 5500
# Open http://localhost:5500/policylens.html
```

### ReviewLens UI

**[web/reviewlens.html](web/reviewlens.html)** — static human-review UI, same pattern as PolicyLens (no build step, served at **`/ui/reviewlens.html`**).

| Area | Features |
|------|----------|
| **Queue** | `GET /review-queue` — oldest first, with verdict band, risk score, fired rules, degraded flag |
| **Case view** | Original creative via `GET /assets/{id}/media`, verdict details, policy pack + hash, LLM advisory (marked non-authoritative) |
| **Labels** | Per-violation *false positive* checkboxes — stored in `review_decisions.violation_feedback` for rule tuning and future model training |
| **Decision** | Approve / Needs changes / Reject with reason; `POST /assets/{id}/review`; asset transitions to `final_*` and an audit event is written |

See [web/README.md](web/README.md). Legacy [web/sentrilens.html](web/sentrilens.html) redirects to PolicyLens.

---

## Database & Persistence

The pipeline persists the full compliance graph to PostgreSQL when `persist=True` (default):

- **assets** — Ingested content with content hash, type, `storage_uri` (ObjectStore), `external_ref`, `parent_asset_id` (revision chains), `metadata`, and `review_state` lifecycle
- **signals** — Extracted features from each extractor
- **violations** — Rule hits with severity, linked to the triggering signal
- **evidence** — Violation evidence linked to signals
- **verdicts** — Final decision with risk score and result (metadata includes policy pack snapshot + `content_hash`, and `degraded_extractors` when extraction partially failed)
- **review_decisions** — Recorded human decisions: reviewer, decision, reason, source, per-violation true/false-positive labels
- **audit_events** — Immutable trail for each compliance check and review decision

Original media bytes are stored outside Postgres in the **ObjectStore** (content-addressed by sha256):

| Variable | Purpose | Default |
|----------|---------|---------|
| `ZATAONE_OBJECT_STORE_DIR` | Local disk root for stored media | `data/objects` |
| `ZATAONE_OBJECT_STORE_BUCKET` | GCS bucket (takes precedence; use on Cloud Run) | unset |
| `ZATAONE_STUCK_ASSET_TIMEOUT_MIN` | Reaper: minutes before a `processing` asset is marked failed | `30` |
| `ZATAONE_REAPER_INTERVAL_S` | Reaper sweep interval (0 disables the loop) | `300` |

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
psql $DATABASE_URL -f migrations/add_review_workflow_and_media.sql   # review workflow, media, lineage
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
- `tests/test_review_workflow.py` — Review queue-entry rules, label sanitization, ObjectStore round-trip, degraded-extraction reporting (no DB required)

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

**Web UI:** `web/policylens.html` (**PolicyLens**) is served at **`/ui/policylens.html`**; `web/reviewlens.html` (**ReviewLens**, human review queue) at **`/ui/reviewlens.html`**. Set **`GEMINI_*`** and **`CORS_ORIGINS`** on the Cloud Run service for advisory review from the browser (see *Advisory review* above). On Cloud Run also set **`ZATAONE_OBJECT_STORE_BUCKET`** so stored media survives instance recycling. **`/ui/sentrilens.html`** redirects to PolicyLens.

---

## Strategic Roadmap (current priorities)

Ordered by priority. The defensible moat is the combination of a deep policy corpus, a labeled evaluation dataset with measured precision/recall, and real-world enforcement data from pilot customers.

| # | Priority | Status |
|---|----------|--------|
| 1 | **Deep ad policy corpus** (Meta / Google / TikTok first) | In progress |
| 2 | **Large evaluation dataset + benchmarks** (clause-level labels, precision/recall per policy category) | Next |
| 3 | **Pilot customers** (real content → labeled enforcement data flywheel) | Next |
| 4 | **Government grants** (SBIR, innovation programs — non-dilutive, in parallel) | Planned |
| 5 | **Government contracts** | Later (after pilots) |
| 6 | **Additional domains** (finance, healthcare, etc.) | After proving ads |

Items 1–3 run in parallel and feed each other: deepening the corpus, building the eval set, and onboarding pilots compound together.

The canonical compliance ontology (schema, categories, cross-source mappings, eval seed) lives in [`ontology/`](ontology/README.md) — one unified corpus where every platform and regulator policy maps into the same schema.

### Platform roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **Foundation** | PostgreSQL, ingestion API, extractors, policy engine, PolicyLens UI | In progress |
| **Explainability** | Document layer, policy corpus, BM25 retrieval, DSL pilot, graph metadata | Shipped (flags default off) |
| **Full cycle** | Media persistence (ObjectStore), human review workflow + ReviewLens UI, per-violation labels, revision chains (`parent_asset_id`), fail-to-review degradation, stuck-asset reaper, policy pack hash stamping | Shipped |
| **MVP** | Additional policy packs, hardened auth, audit exports | Planned |
| **Scale** | Multi-tenancy, webhooks, video pipeline, 10+ packs | Planned |
| **Platform** | Policy builder UI, extractor SDK, marketplace, SOC 2 | Planned |

---

## License

See [LICENSE](LICENSE) for details.
