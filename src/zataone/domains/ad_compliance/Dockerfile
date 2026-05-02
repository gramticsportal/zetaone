# Production Dockerfile for Zataone Ad Compliance API (Cloud Run, CPU-only; domain bundle)
# Python 3.11, gunicorn, models download at runtime

FROM python:3.11-slim-bookworm

# Prevent Python from writing pyc and buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Cloud Run sets PORT; default for local runs
ENV PORT=8080

# CPU-only: ensure no CUDA/GPU assumptions
ENV CUDA_VISIBLE_DEVICES=""
ENV TORCH_USE_CUDA_DSA=0

# Install system deps: tesseract for OCR (models download at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PyTorch CPU-only first (avoid CUDA from PyPI)
# https://download.pytorch.org/whl/cpu - prevents any NVIDIA/CUDA packages
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining deps (exclude torch so it is not pulled from requirements.txt)
COPY requirements.txt .
RUN grep -v '^torch' requirements.txt > /tmp/requirements-no-torch.txt && \
    pip install --no-cache-dir -r /tmp/requirements-no-torch.txt gunicorn

# Copy application (no models; they download at runtime)
COPY . .

# Gunicorn: bind to 0.0.0.0:$PORT, 1 worker for Cloud Run cold-start optimization
# Use sync worker; ML inference is CPU-bound. Shell form so $PORT is expanded.
CMD gunicorn --bind 0.0.0.0:${PORT} --workers 1 --threads 4 --timeout 300 app:app
