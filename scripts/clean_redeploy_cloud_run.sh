#!/usr/bin/env bash
# Clean old Cloud Run revisions (optional), build a fresh image, deploy by digest, verify UI.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-zetaone-493600}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-zetaone-api}"
IMAGE_TAG="${IMAGE_TAG:-phase4-$(date +%Y%m%d-%H%M%S)}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

cd "$REPO_ROOT"

echo "==> Sanity check local PolicyLens"
wc -c web/policylens.html
grep -c pipelineModeRow web/policylens.html

echo "==> Delete old Cloud Run revisions (keeps newest; macOS-safe, no mapfile)"
n=0
for rev in $(gcloud run revisions list \
  --service="$SERVICE" \
  --region="$REGION" \
  --project="$PROJECT_ID" \
  --format="value(metadata.name)" 2>/dev/null || true); do
  n=$((n + 1))
  [[ "$n" -eq 1 ]] && continue
  echo "    deleting revision $rev"
  gcloud run revisions delete "$rev" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --quiet || true
done

echo "==> Cloud Build (tag: $IMAGE_TAG)"
gcloud builds submit --config cloudbuild.yaml \
  --project="$PROJECT_ID" \
  --substitutions="_REGION=${REGION},_HF_TOKEN=${HF_TOKEN:-},_IMAGE_TAG=${IMAGE_TAG}"

BUILD_ID=$(gcloud builds list --project="$PROJECT_ID" --limit=1 --format='value(id)')
DIGEST=$(gcloud builds describe "$BUILD_ID" --project="$PROJECT_ID" \
  --format='value(results.images[0].digest)')

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/zataone/zataone-api@${DIGEST}"
echo "==> Deploy $IMAGE"
gcloud run services update "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$IMAGE"

echo "==> Verify"
BASE="https://zetaone-api-606898132436.us-central1.run.app"
curl -sS "${BASE}/health/ui-asset" | python3 -m json.tool || curl -sS "${BASE}/health/ui-asset"
echo ""
curl -sSI "${BASE}/ui/policylens.html" | grep -i content-length || true
curl -sS "${BASE}/ui/policylens.html" | grep -o pipelineMode | head -1 || echo "(no pipelineMode in HTML yet)"
echo "Done. Open ${BASE}/ui/policylens.html (hard refresh)."
