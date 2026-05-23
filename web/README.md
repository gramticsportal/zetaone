# ZataOne demo UI (static)

## Pages

| File | Purpose |
|------|--------|
| **`policylens.html`** | **PolicyLens** — Full/Quick pipeline toggle, upload → poll → verdict, explainability graph, overlays (Full), inline Gemini advisory |
| **`sentrilens.html`** | Redirects to `policylens.html` (legacy path). |
| **`index.html`** | Minimal JSON viewer (links to PolicyLens for the full UI). |

## Pipeline modes (UI)

| Mode | UI progress | Backend |
|------|-------------|---------|
| **Full** | Upload → Extraction → Document → Retrieval → Policy/LLM → Result | Extractors + VLM ∥ core + LLM vs policy (YAML engine optional via API env) |
| **Quick** | Upload → VLM → LLM vs policy → Result | No extractors; LLM vs policy corpus (combined Gemini pass when API has `ZATAONE_FAST_COMBINED_REVIEW=true`) |

Send **`X-Pipeline-Mode: full`** or **`fast`** on upload (PolicyLens sets this automatically).

## Use locally

1. Run the API (e.g. `uvicorn zataone.main:app --reload --port 8000`).
2. Serve this folder over HTTP (browsers block `file://` for CORS/fetch):

```bash
cd web && python -m http.server 5500
```

3. Open **`http://localhost:5500/policylens.html`** — set **API base URL** to `http://127.0.0.1:8000` or your Cloud Run URL.

## Use with Cloud Run

1. Deploy the API (see `docs/deploy-gcp-step-by-step.md` and root `README.md`).
2. Set **`CORS_ORIGINS`** to your static site origin (e.g. `https://underintelligence.com`).
3. Host `web/policylens.html` on your static host **or** use **`https://<service>/ui/policylens.html`** from the API image.
4. API base URL (no trailing slash), e.g. `https://zataone-api-606898132436.us-central1.run.app`.

Deploy image path: `us-central1-docker.pkg.dev/PROJECT_ID/zataone/zataone-api:TAG` → service **`zataone-api`**.
