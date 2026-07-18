# zataone Dockerfile
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Hub cache baked into image (~0.5–1.5GB depending on models; avoids runtime downloads).
ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
ENV HF_HUB_CACHE=/app/.cache/huggingface/hub

COPY requirements.txt /tmp/requirements.txt
# Install non-torch deps from PyPI, then CPU-only torch/torchvision from PyTorch wheel index.
RUN sed '/^torch/d' /tmp/requirements.txt > /tmp/req-notorch.txt \
  && pip install --no-cache-dir -r /tmp/req-notorch.txt \
  && pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Optional: docker build --build-arg HF_TOKEN=hf_... (Cloud Build: --substitutions=_HF_TOKEN=...)
ARG HF_TOKEN
ENV HF_TOKEN=${HF_TOKEN}

# Separate layers so peak RAM is one model at a time (helps Cloud Build on smaller workers).
COPY docker/preload_models.py /tmp/preload_models.py
RUN python /tmp/preload_models.py dino
RUN python /tmp/preload_models.py siglip
RUN python /tmp/preload_models.py minilm
RUN rm -f /tmp/preload_models.py

COPY . .
RUN pip install --no-cache-dir -e .
ENV ZATAONE_WEB_DIR=/app/web
RUN grep -q pipelineModeRow /app/web/policylens.html \
    && test "$(wc -c < /app/web/policylens.html)" -gt 80000

# Cloud Run sets PORT (default 8080). Local: docker run -p 8000:8000 -e PORT=8000
ENV PORT=8000
# Use domain OCR / Vision / Embedding / VLM; skip duplicate core stubs (see CompliancePipeline).
ENV ZATAONE_DISABLE_CORE_STUB_EXTRACTORS=true

CMD uvicorn zataone.main:app --host 0.0.0.0 --port ${PORT}
