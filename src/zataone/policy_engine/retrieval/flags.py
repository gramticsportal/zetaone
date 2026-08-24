# zataone policy retrieval feature flags

from __future__ import annotations

import os


def policy_retrieval_enabled() -> bool:
    v = os.environ.get("ZATAONE_POLICY_RETRIEVAL", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return True


def retrieval_top_k() -> int:
    """
    BM25 shortlist size. Default 32 (under-filter) when hybrid engine is on,
    else 8. Override with ZATAONE_RETRIEVAL_TOP_K.
    """
    raw = os.environ.get("ZATAONE_RETRIEVAL_TOP_K", "").strip()
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            pass
    # Prefer under-filter when hybrid is active
    try:
        from zataone.policy_engine.hybrid.flags import hybrid_engine_enabled

        if hybrid_engine_enabled():
            try:
                from zataone.policy_engine.hybrid.flags import hybrid_retrieval_top_k

                return hybrid_retrieval_top_k()
            except Exception:
                return 32
    except Exception:
        pass
    return 8


def retrieval_fallback_all() -> bool:
    v = os.environ.get("ZATAONE_RETRIEVAL_FALLBACK_ALL", "true").strip().lower()
    return v not in ("0", "false", "no", "off")
