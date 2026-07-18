#!/usr/bin/env python3
"""
Pre-download Hugging Face weights into HF_HOME during Docker build.
Use: python preload_models.py [dino|siglip|all]  — split steps reduce peak RAM during docker build.
"""
from __future__ import annotations

import argparse
import os
import sys

GROUNDING_DINO_ID = "IDEA-Research/grounding-dino-base"
SIGLIP_ID = "google/siglip-base-patch16-224"
MINILM_ID = "sentence-transformers/all-MiniLM-L6-v2"


def _kwargs():
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    return {"token": token} if token else {}


def preload_dino() -> None:
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    kw = _kwargs()
    print("Preloading Grounding DINO:", GROUNDING_DINO_ID, flush=True)
    p = AutoProcessor.from_pretrained(GROUNDING_DINO_ID, **kw)
    m = AutoModelForZeroShotObjectDetection.from_pretrained(GROUNDING_DINO_ID, **kw)
    del p, m


def preload_siglip() -> None:
    from transformers import AutoModel, AutoProcessor

    kw = _kwargs()
    print("Preloading SigLIP:", SIGLIP_ID, flush=True)
    p = AutoProcessor.from_pretrained(SIGLIP_ID, **kw)
    m = AutoModel.from_pretrained(SIGLIP_ID, **kw)
    del p, m


def preload_minilm() -> None:
    """Phase B hybrid NLP — bake MiniLM so Cloud Run cold starts skip Hub download."""
    from transformers import AutoModel, AutoTokenizer

    kw = _kwargs()
    print("Preloading MiniLM:", MINILM_ID, flush=True)
    t = AutoTokenizer.from_pretrained(MINILM_ID, **kw)
    m = AutoModel.from_pretrained(MINILM_ID, **kw)
    del t, m


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "which",
        nargs="?",
        default="all",
        choices=("all", "dino", "siglip", "minilm"),
        help="Which model(s) to download (default: all)",
    )
    args = ap.parse_args()
    if args.which in ("all", "dino"):
        preload_dino()
    if args.which in ("all", "siglip"):
        preload_siglip()
    if args.which in ("all", "minilm"):
        preload_minilm()
    cache = os.environ.get("HF_HOME") or os.environ.get("TRANSFORMERS_CACHE", "")
    print("Model preload step done. Cache:", cache, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
