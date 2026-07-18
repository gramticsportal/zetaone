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
    try:
        return max(1, int(os.environ.get("ZATAONE_RETRIEVAL_TOP_K", "8")))
    except ValueError:
        return 8


def retrieval_fallback_all() -> bool:
    v = os.environ.get("ZATAONE_RETRIEVAL_FALLBACK_ALL", "true").strip().lower()
    return v not in ("0", "false", "no", "off")
