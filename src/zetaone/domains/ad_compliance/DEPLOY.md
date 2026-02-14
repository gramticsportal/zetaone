# Cloud Run Deployment

## Copy-paste-ready gcloud commands

```bash
# 1. Set project (replace with your GCP project ID)
export PROJECT_ID=your-gcp-project-id
gcloud config set project $PROJECT_ID

# 2. Enable required APIs
gcloud services enable run.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable artifactregistry.googleapis.com

# 3. Create Artifact Registry repository (one-time)
gcloud artifacts repositories create compliance-ai-repo \
  --repository-format=docker \
  --location=us-central1 \
  --description="Compliance AI container images" \
  || true

# 4. Build container via Cloud Build
gcloud builds submit --tag us-central1-docker.pkg.dev/$PROJECT_ID/compliance-ai-repo/compliance-ai:latest .

# 5. Deploy to Cloud Run
gcloud run deploy compliance-ai \
  --image us-central1-docker.pkg.dev/$PROJECT_ID/compliance-ai-repo/compliance-ai:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --timeout 300 \
  --set-env-vars "VLM_API_KEY=your-openai-api-key"
```

## First deployment checklist

- [ ] GCP project created and billing enabled
- [ ] `gcloud auth login` and `gcloud config set project PROJECT_ID`
- [ ] `VLM_API_KEY` set (OpenAI API key for GPT-4o Vision)
- [ ] APIs enabled (Run, Cloud Build, Artifact Registry)
- [ ] Build succeeds: `gcloud builds submit --tag ...`
- [ ] Deploy succeeds; note the service URL
- [ ] Health check: `curl https://SERVICE_URL/health`
- [ ] API test: `curl -X POST https://SERVICE_URL/v1/ads/meta/image/check -F "image=@tests/assets/fixture_with_text.png" -F "domain=ads"`
- [ ] Viewer: open `https://SERVICE_URL/viewer` in browser
