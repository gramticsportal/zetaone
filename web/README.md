# ZataOne demo UI (static)

## Pages

| File | Purpose |
|------|--------|
| **`policylens.html`** | **PolicyLens** — ad/compliance visual review: image/text upload, poll, verdict + violations, **overlays** from `/assets/{id}/graph`, health check, progress steps, **advisory (Gemini)**. |
| **`sentrilens.html`** | Redirects to `policylens.html` (legacy path). |
| **`index.html`** | Minimal JSON viewer (links to PolicyLens for the full UI). |

## Use locally

1. Run the API (e.g. `uvicorn zataone.main:app --reload --port 8000`).
2. Serve this folder over HTTP (browsers block `file://` for CORS/fetch):

```bash
cd web && python -m http.server 5500
```

3. Open **`http://localhost:5500/policylens.html`** (or `index.html`) — set **API base URL** to `http://127.0.0.1:8000` or your Cloud Run URL.

## Use with Cloud Run

1. Deploy the API (see `docs/deploy-gcp-step-by-step.md`).
2. Set **CORS_ORIGINS** on Cloud Run to wherever you host this UI (or use a temporary `CORS_ALLOW_ALL=true` only for testing).
3. Host `web/` on Firebase Hosting, Cloud Storage static site, or any HTTPS static host.
4. Enter your Cloud Run URL (no trailing slash), e.g. `https://zataone-api-xxxxx-uc.a.run.app`.
