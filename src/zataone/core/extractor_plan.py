# zataone per-modality extractor selection (domain-agnostic)

from __future__ import annotations

from typing import Any

from zataone.core.extractor_flags import (
    embedding_enabled,
    pipeline_mode,
    pipeline_vlm_extractor_enabled,
)
from zataone.extractors.base import BaseExtractor

# Short names used in domain YAML extractors.enabled
_SHORT_TO_IDS: dict[str, frozenset[str]] = {
    "ocr": frozenset({"ad_compliance_ocr", "ocr_extractor"}),
    "vision": frozenset({"ad_compliance_vision", "vision_extractor"}),
    "embedding": frozenset({"ad_compliance_embedding", "embedding_extractor"}),
    "vlm": frozenset({"ad_compliance_vlm", "vlm_extractor"}),
    "asr": frozenset({"ad_compliance_asr"}),
    "text": frozenset({"text_extractor"}),
    "video": frozenset({"video_extractor"}),
}

# Default extractors by asset type when YAML list is absent
_DEFAULT_BY_TYPE: dict[str, frozenset[str]] = {
    "text": frozenset({"text_extractor"}),
    "image": frozenset(
        {"text_extractor", "ad_compliance_ocr", "ocr_extractor", "ad_compliance_vision", "vision_extractor"}
    ),
    "audio": frozenset({"text_extractor", "ad_compliance_asr"}),
    "video": frozenset({"text_extractor", "video_extractor", "ad_compliance_ocr", "ocr_extractor"}),
}


def _extractor_id(extractor: BaseExtractor) -> str:
    return getattr(extractor, "extractor_id", None) or type(extractor).__name__


def _yaml_enabled_ids(config: dict) -> set[str] | None:
    ex = config.get("extractors") or {}
    raw = ex.get("enabled")
    if raw is None:
        return None
    if isinstance(raw, list) and len(raw) == 0:
        return None
    out: set[str] = set()
    for short in raw:
        out |= set(_SHORT_TO_IDS.get(str(short).strip().lower(), frozenset()))
    return out


def _allow_extractor_id(eid: str, asset_type: str, yaml_ids: set[str] | None) -> bool:
    at = (asset_type or "text").strip().lower()
    allowed_for_type = _DEFAULT_BY_TYPE.get(at, _DEFAULT_BY_TYPE["text"])

    # Text extractor always allowed for text/audio; YAML list targets heavy modalities.
    if eid in _SHORT_TO_IDS["text"] and at in ("text", "audio"):
        return True

    if yaml_ids is not None:
        if eid not in yaml_ids:
            return False
    elif eid not in allowed_for_type:
        return False

    if eid in _SHORT_TO_IDS["embedding"] and not embedding_enabled():
        return False
    if eid in _SHORT_TO_IDS["vlm"] and not pipeline_vlm_extractor_enabled():
        return False
    if eid in _SHORT_TO_IDS["asr"] and at != "audio":
        return False
    if eid in _SHORT_TO_IDS["ocr"] | _SHORT_TO_IDS["vision"] and at == "text":
        return False
    if eid in _SHORT_TO_IDS["ocr"] | _SHORT_TO_IDS["vision"] | _SHORT_TO_IDS["embedding"]:
        if at not in ("image", "video"):
            return False

    return True


def select_extractors_for_asset(
    extractors: list[BaseExtractor],
    asset: Any,
    domain_config: dict | None = None,
    *,
    run_pipeline_mode: str | None = None,
) -> list[BaseExtractor]:
    """Filter registered extractors by asset modality and global flags."""
    if (run_pipeline_mode or pipeline_mode()) == "fast":
        return []
    config = domain_config or {}
    asset_type = getattr(asset, "type", None) or "text"
    yaml_ids = _yaml_enabled_ids(config)
    selected = []
    for ext in extractors:
        eid = _extractor_id(ext)
        if _allow_extractor_id(eid, asset_type, yaml_ids):
            selected.append(ext)
    return selected


def allow_domain_short_name(short: str, config: dict | None = None) -> bool:
    """Whether to register a domain extractor class at pipeline init."""
    config = config or {}
    enabled = _yaml_enabled_ids(config)
    s = short.strip().lower()
    if enabled is not None:
        return s in {x.strip().lower() for x in (config.get("extractors") or {}).get("enabled", [])}
    if s == "embedding":
        return embedding_enabled()
    if s == "vlm":
        return pipeline_vlm_extractor_enabled()
    return s in ("ocr", "vision", "asr", "text")
