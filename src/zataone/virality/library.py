from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_DATA = Path(__file__).resolve().parent.parent / "data" / "viral_ad_patterns.yaml"


@lru_cache(maxsize=1)
def load_viral_patterns() -> list[dict[str, Any]]:
    if not _DATA.is_file():
        return []
    doc = yaml.safe_load(_DATA.read_text(encoding="utf-8")) or {}
    return list(doc.get("patterns") or [])


def patterns_for_prompt(max_items: int = 40) -> str:
    lines = []
    for p in load_viral_patterns()[:max_items]:
        lines.append(
            f"- {p.get('id')}: {p.get('name')} — example: {p.get('snippet')!r} "
            f"tags={p.get('tags') or []}"
        )
    return "\n".join(lines) if lines else "(no library loaded)"
