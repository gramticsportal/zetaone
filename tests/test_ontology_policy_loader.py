"""Ontology corpus → runtime PolicyPack clause integration tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.policy_engine.corpus.loader import load_policy_pack_from_path
from zataone.policy_engine.corpus.ontology_loader import (
    load_ontology_clauses,
    merge_ontology_clauses_into_pack,
    resolve_ontology_root,
)


@pytest.fixture
def ontology_root():
    root = resolve_ontology_root()
    if root is None:
        pytest.skip("ontology/ not found")
    return root


def test_resolve_ontology_root(ontology_root):
    assert (ontology_root / "schema.yaml").is_file()
    assert (ontology_root / "corpus" / "meta_ads_us.yaml").is_file()


def test_load_ontology_clauses_us(ontology_root):
    clauses = load_ontology_clauses(jurisdiction="US", ontology_root=ontology_root)
    assert len(clauses) >= 50
    ids = {c.clause_id for c in clauses}
    assert "meta.misleading.exaggerated_success_claims" in ids
    assert any(c.text.strip() for c in clauses)


def test_merge_ontology_clauses_into_runtime_pack(ontology_root):
    path = (
        Path(__file__).resolve().parent.parent
        / "src/zataone/domains/ad_compliance/policies/meta_ads.yaml"
    )
    pack = load_policy_pack_from_path(path)
    n_legacy = len(pack.clauses)
    ont = load_ontology_clauses(
        jurisdiction="US",
        corpus_files=("meta_ads_us.yaml",),
        ontology_root=ontology_root,
    )
    merge_ontology_clauses_into_pack(pack, ont)
    assert len(pack.clauses) > n_legacy
    assert len(pack.rules) >= 3
    assert "misleading_exaggerated_claims" in pack.rules
