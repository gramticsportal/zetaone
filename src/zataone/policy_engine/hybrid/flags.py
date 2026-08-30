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
    Default ON — 54 packs are cheap; shortlist under-filtered financial FNs.
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


def semantic_classifier_enabled() -> bool:
    """Run the learned tier as a sensor alongside the lexical packs.

    Off by default. When on it never raises a violation — it recommends human review for
    copy the packs had no rule for. On the held-out split that recovers 86% of the
    violations tier 1 misses, at the cost of flagging 38% of the clean copy tier 1 cleared,
    so it buys recall with reviewer time and the trade should be a deployment decision.
    """
    return _env_bool("ZATAONE_SEMANTIC_CLASSIFIER", default=False)


def hybrid_min_confidence() -> float:
    """Drop lexical hits whose measured confidence is below this.

    Off (0.0) by default: the shipped constants were uniform, so a threshold over them
    would have been arbitrary. It becomes meaningful once confidence.yaml is present,
    because then the number is measured per pack and matcher on the dev split.
    """
    try:
        return max(0.0, min(1.0, float(os.environ.get("ZATAONE_HYBRID_MIN_CONFIDENCE", "0"))))
    except ValueError:
        return 0.0


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
