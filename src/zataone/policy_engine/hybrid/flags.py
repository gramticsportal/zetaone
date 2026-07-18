# zataone hybrid engine feature flags

from __future__ import annotations

import os


def _env_bool(name: str, *, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def hybrid_engine_enabled() -> bool:
    """
    Use Phase B hybrid pattern packs + NLP as the deterministic engine.
    Default ON when unset (rollback: ZATAONE_HYBRID_ENGINE=0).
    """
    return _env_bool("ZATAONE_HYBRID_ENGINE", default=True)


def hybrid_nlp_enabled() -> bool:
    """
    Run embedding/NLP scorer alongside lexical matchers.
    Default OFF — lexical is primary; re-enable with ZATAONE_HYBRID_NLP=1.
    """
    return _env_bool("ZATAONE_HYBRID_NLP", default=False)


def hybrid_all_packs() -> bool:
    """
    Evaluate every approved pattern pack (skip BM25-style shortlist).
    Default ON — 52 packs are cheap; shortlist under-filtered financial FNs.
    Rollback: ZATAONE_HYBRID_ALL_PACKS=0.
    """
    return _env_bool("ZATAONE_HYBRID_ALL_PACKS", default=True)


def hybrid_nlp_backend() -> str:
    """
    NLP backend: auto | bow | minilm | minilm_l12 | bge_small | e5_small
    auto = MiniLM-L6 via transformers if loadable, else bag-of-words cosine.
    Optional override: ZATAONE_HYBRID_NLP_MODEL=<hf_model_id>
    """
    v = (os.environ.get("ZATAONE_HYBRID_NLP_BACKEND") or "auto").strip().lower().replace("-", "_")
    allowed = ("auto", "bow", "minilm", "minilm_l12", "bge_small", "e5_small")
    return v if v in allowed else "auto"


def hybrid_nlp_model_id() -> str | None:
    """Optional explicit HuggingFace model id for the transformer NLP backend."""
    v = (os.environ.get("ZATAONE_HYBRID_NLP_MODEL") or "").strip()
    return v or None


def hybrid_retrieval_top_k() -> int:
    """Under-filter shortlist size for hybrid (prefer high K). Default 32."""
    try:
        return max(8, int(os.environ.get("ZATAONE_HYBRID_RETRIEVAL_TOP_K", "32")))
    except ValueError:
        return 32


def hybrid_nlp_threshold() -> float:
    try:
        return float(os.environ.get("ZATAONE_HYBRID_NLP_THRESHOLD", "0.55"))
    except ValueError:
        return 0.55


# Categories always evaluated even if BM25 misses them (under-filter).
ALWAYS_INCLUDE_CATEGORIES: frozenset[str] = frozenset(
    {
        "health",
        "political",
        "gambling",
        "drugs",
        "discrimination",
        "misleading",
    }
)
