# zataone — optional ontology corpus integration flags

from __future__ import annotations

import os


def _env_bool(name: str, *, default: bool = False) -> bool:
    v = os.environ.get(name, "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return default


def ontology_pack_enabled() -> bool:
    """Use ontology/corpus as primary PolicyPack (US). Default ON."""
    return _env_bool("ZATAONE_ONTOLOGY_PACK", default=True)


def ontology_clauses_enabled() -> bool:
    """Legacy: merge ontology clauses into meta_ads pack. Ignored when ontology pack is on."""
    return _env_bool("ZATAONE_ONTOLOGY_CLAUSES", default=True)


def legacy_meta_policy_only() -> bool:
    """Force legacy meta_ads.yaml instead of ontology pack."""
    return _env_bool("ZATAONE_LEGACY_META_POLICY", default=False)
