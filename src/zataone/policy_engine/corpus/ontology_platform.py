# zataone — ad platform filter for ontology corpus (US)

from __future__ import annotations

# Clause id prefix -> platform slug (X-Platform / metadata.platform).
_PLATFORM_PREFIXES: dict[str, tuple[str, ...]] = {
    "all": (),  # no filter
    "meta": ("meta.",),
    "google": ("google.",),
    "tiktok": ("tiktok.",),
    "linkedin": ("linkedin.",),
    "amazon": ("amazon.",),
    "snapchat": ("snapchat.",),
    "pinterest": ("pinterest.",),
    "reddit": ("reddit.",),
    "microsoft": ("microsoft.",),
    "x": ("x.",),
}

# Regulator clause prefixes always apply when a specific platform is chosen.
_REGULATOR_PREFIXES: tuple[str, ...] = (
    "ftc.",
    "fda.",
    "sec.",
    "finra.",
    "cfpb.",
    "hud.",
    "eeoc.",
    "fec.",
    "ccpa.",
    "ttb.",
)


def normalize_platform(platform: str | None) -> str:
    p = (platform or "all").strip().lower()
    return p if p in _PLATFORM_PREFIXES else "all"


def clause_matches_platform(clause_id: str, platform: str) -> bool:
    """True if clause applies under platform filter (US)."""
    platform = normalize_platform(platform)
    if platform == "all":
        return True
    cid = (clause_id or "").lower()
    for prefix in _REGULATOR_PREFIXES:
        if cid.startswith(prefix):
            return True
    for prefix in _PLATFORM_PREFIXES.get(platform, ()):
        if cid.startswith(prefix):
            return True
    return False


def filter_clause_ids(clause_ids: list[str], platform: str) -> list[str]:
    return [c for c in clause_ids if clause_matches_platform(c, platform)]


def filter_rule_ids_for_platform(
    rules: dict[str, dict],
    platform: str,
) -> set[str] | None:
    """
    Return rule ids to evaluate, or None for all rules (platform=all).
    """
    platform = normalize_platform(platform)
    if platform == "all":
        return None
    out: set[str] = set()
    for rid, rule in rules.items():
        cids = rule.get("clause_ids") or []
        if any(clause_matches_platform(str(c), platform) for c in cids):
            out.add(rid)
    return out
