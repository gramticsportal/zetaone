"""API platform metadata helper tests."""

from __future__ import annotations

import sys
from pathlib import Path

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.api.routes import _merge_platform_metadata


def test_merge_platform_defaults_all():
    assert _merge_platform_metadata(None, None)["platform"] == "all"


def test_merge_platform_header():
    meta = _merge_platform_metadata(None, "meta")
    assert meta["platform"] == "meta"


def test_merge_platform_body_overrides_header():
    meta = _merge_platform_metadata({"platform": "google"}, "meta")
    assert meta["platform"] == "google"
