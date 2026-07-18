"""Ontology pack builder and platform filter tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.policy_engine.corpus.ontology_flags import (
    legacy_meta_policy_only,
    ontology_pack_enabled,
)
from zataone.policy_engine.corpus.ontology_loader import resolve_ontology_root
from zataone.policy_engine.corpus.ontology_pack_builder import (
    build_ontology_policy_pack,
    filter_pack_for_platform,
)
from zataone.policy_engine.corpus.ontology_platform import (
    clause_matches_platform,
    normalize_platform,
)


@pytest.fixture
def ontology_root():
    root = resolve_ontology_root()
    if root is None:
        pytest.skip("ontology/ not found")
    return root


def test_default_flags_ontology_pack_on(monkeypatch):
    monkeypatch.delenv("ZATAONE_ONTOLOGY_PACK", raising=False)
    monkeypatch.delenv("ZATAONE_LEGACY_META_POLICY", raising=False)
    assert ontology_pack_enabled() is True
    assert legacy_meta_policy_only() is False


def test_build_ontology_policy_pack_us_all(ontology_root):
    pack = build_ontology_policy_pack(
        jurisdiction="US",
        platform="all",
        ontology_root=ontology_root,
    )
    assert pack is not None
    assert len(pack.clauses) >= 100
    assert len(pack.rules) >= 50
    assert pack.id.startswith("ontology_us_")


def test_platform_filter_meta(ontology_root):
    full = build_ontology_policy_pack(
        jurisdiction="US",
        platform="all",
        ontology_root=ontology_root,
    )
    assert full is not None
    meta = filter_pack_for_platform(full, "meta")
    assert len(meta.clauses) < len(full.clauses)
    assert len(meta.clauses) >= 10
    assert all(clause_matches_platform(c.clause_id, "meta") for c in meta.clauses)
    assert len(meta.rules) >= 5


def test_normalize_platform_unknown_defaults_all():
    assert normalize_platform("bogus") == "all"
    assert normalize_platform(None) == "all"
    assert normalize_platform("META") == "meta"
