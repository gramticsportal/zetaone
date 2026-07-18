# zataone extractor feature flags (domain-agnostic)

from __future__ import annotations

import os


def _env_bool(name: str, *, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def embedding_enabled() -> bool:
    """SigLIP embedding extractor (off by default for speed)."""
    return _env_bool("ZATAONE_ENABLE_EMBEDDING", default=False)


def ocr_enabled() -> bool:
    """
    Local OCR (Tesseract). Default OFF — Gemini VLM supplies ocr_text for images.
    Re-enable: ZATAONE_ENABLE_OCR=1.
    """
    return _env_bool("ZATAONE_ENABLE_OCR", default=False)


def vision_dino_enabled() -> bool:
    """
    Grounding DINO local object detector. Default OFF — VLM supplies objects[].
    Re-enable: ZATAONE_ENABLE_VISION=1.
    """
    return _env_bool("ZATAONE_ENABLE_VISION", default=False)


def pipeline_vlm_extractor_enabled() -> bool:
    """GPT/OpenAI VLM during extraction (off; use Gemini advisory VLM instead)."""
    return _env_bool("ZATAONE_ENABLE_PIPELINE_VLM", default=False)


def pipeline_parallel_vlm_enabled() -> bool:
    """
    Legacy: run Gemini VLM in parallel with OCR/DINO extraction.
    When OCR+DINO are off (default), Full image path runs VLM *before* hybrid
    so structured VLM text can feed the deterministic matcher; this flag is
    ignored in that VLM-primary mode.
    """
    return _env_bool("ZATAONE_PARALLEL_VLM", default=True)


def vlm_primary_image_path() -> bool:
    """True when local OCR and DINO are both off — VLM owns image→text."""
    return (not ocr_enabled()) and (not vision_dino_enabled())


def pipeline_parallel_extractors_enabled() -> bool:
    """Run registered extractors concurrently."""
    return _env_bool("ZATAONE_PARALLEL_EXTRACTORS", default=True)


def pipeline_mode() -> str:
    """full = extractors + optional rule engine + advisory; fast = VLM then LLM vs policy."""
    v = (os.environ.get("ZATAONE_PIPELINE_MODE") or "full").strip().lower()
    return "fast" if v == "fast" else "full"


def policy_engine_enabled() -> bool:
    """YAML rule-engine evaluation on signals. Default ON with ontology pack."""
    return _env_bool("ZATAONE_POLICY_ENGINE_ENABLED", default=True)


def hybrid_engine_enabled() -> bool:
    """
    Phase B hybrid (pattern packs + NLP) replaces legacy PolicyEngine when ON.
    Default ON. Rollback: ZATAONE_HYBRID_ENGINE=0.
    """
    from zataone.policy_engine.hybrid.flags import hybrid_engine_enabled as _h

    return _h()


def display_verdict_from_llm() -> bool:
    """
    When True (default), Full pipeline uses LLM synthesis as user-visible verdict.
    Rule engine outcomes remain in metadata for explainability/audit.
    Set ZATAONE_VERDICT_AUTHORITY=deterministic to restore rule-engine display.
    """
    v = (os.environ.get("ZATAONE_VERDICT_AUTHORITY") or "advisory").strip().lower()
    return v not in ("deterministic", "rules", "engine")


def fast_combined_review_enabled() -> bool:
    """Quick image path: one Gemini vision+policy call instead of VLM then text LLM."""
    return _env_bool("ZATAONE_FAST_COMBINED_REVIEW", default=True)


def pipeline_auto_advisory_enabled() -> bool:
    """Run Gemini advisory synthesis at end of pipeline when API key is set."""
    if os.environ.get("ZATAONE_PIPELINE_ADVISORY", "").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    if os.environ.get("ZATAONE_PIPELINE_ADVISORY", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return True
    return bool(
        (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    )
