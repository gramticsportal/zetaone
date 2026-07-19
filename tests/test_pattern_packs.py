"""Unit tests for pattern-pack vocabulary augmentation (data-only adoption)."""

import sys
from pathlib import Path

# Ensure src is first for correct zataone import
src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

import pytest

from zataone.policy_engine.corpus.pattern_packs import (
    augment_rules_with_packs,
    load_pattern_packs,
)

ONTOLOGY_ROOT = Path(__file__).resolve().parent.parent / "ontology"


def _fake_pack(**over):
    pack = {
        "canonical_id": "atc.test_pack",
        "category_id": "alcohol",
        "severity": "high",
        "review_status": "approved",
        "source_rule_ids": ["google_atc_alcohol"],
        "clause_ids": ["google.atc.alcohol"],
        "forbidden_terms": ["beer"],
        "forbidden_phrases": ["buy beer", "happy hour special"],
        "forbidden_patterns": [{"pattern": r"\bdrink\s+now\b", "confidence": 0.8}],
        "exceptions": {"terms": ["results may vary"], "phrases": []},
        "requires_context": {"terms": ["alcohol", "beer"]},
    }
    pack.update(over)
    return pack


def _augment(monkeypatch, rules, packs, **env):
    defaults = {
        "ZATAONE_PATTERN_PACKS": "1",
        "ZATAONE_PACK_TERMS": "0",
        "ZATAONE_PACK_CONTEXT_GATE": "0",
        "ZATAONE_PACK_REPLACE_TERMS": "0",
    }
    defaults.update(env)
    for k, v in defaults.items():
        monkeypatch.setenv(k, v)
    import zataone.policy_engine.corpus.pattern_packs as mod

    monkeypatch.setattr(mod, "load_pattern_packs", lambda root: packs)
    return mod.augment_rules_with_packs(rules, Path("."))


def test_merge_adds_phrases_patterns_exceptions(monkeypatch):
    rules = {"google_atc_alcohol": {"prohibited_terms": ["under-18"]}}
    stats = _augment(monkeypatch, rules, [_fake_pack()])
    rule = rules["google_atc_alcohol"]
    assert stats["augmented_rules"] == 1
    assert "buy beer" in rule["prohibited_terms"]
    assert "under-18" in rule["prohibited_terms"]  # merge keeps existing
    assert "beer" not in rule["prohibited_terms"]  # single terms off by default
    assert rule["patterns"][0]["pattern"] == r"\bdrink\s+now\b"
    assert "results may vary" in rule["exception_terms"]
    assert "context_terms" not in rule  # gate off by default


def test_terms_flag_includes_single_terms(monkeypatch):
    rules = {"google_atc_alcohol": {}}
    _augment(monkeypatch, rules, [_fake_pack()], ZATAONE_PACK_TERMS="1")
    assert "beer" in rules["google_atc_alcohol"]["prohibited_terms"]


def test_replace_drops_naive_terms(monkeypatch):
    rules = {"google_atc_alcohol": {"prohibited_terms": ["naive", "tokens"]}}
    _augment(monkeypatch, rules, [_fake_pack()], ZATAONE_PACK_REPLACE_TERMS="1")
    terms = rules["google_atc_alcohol"]["prohibited_terms"]
    assert "naive" not in terms and "buy beer" in terms


def test_unmatched_pack_becomes_standalone_rule(monkeypatch):
    rules = {}
    stats = _augment(
        monkeypatch, rules, [_fake_pack(source_rule_ids=["missing_rule"])]
    )
    assert stats["standalone_rules"] == 1
    assert "pack_atc.test_pack" in rules
    assert "buy beer" in rules["pack_atc.test_pack"]["prohibited_terms"]


def test_disabled_flag_is_noop(monkeypatch):
    rules = {"google_atc_alcohol": {"prohibited_terms": ["x"]}}
    stats = _augment(monkeypatch, rules, [_fake_pack()], ZATAONE_PATTERN_PACKS="0")
    assert stats == {"packs": 0, "augmented_rules": 0, "standalone_rules": 0}
    assert rules["google_atc_alcohol"]["prohibited_terms"] == ["x"]


def test_real_pack_files_load():
    if not (ONTOLOGY_ROOT / "patterns" / "by_category").is_dir():
        pytest.skip("ontology/patterns not present")
    packs = load_pattern_packs(ONTOLOGY_ROOT)
    assert len(packs) == 52
    assert all(p.get("category_id") for p in packs)
