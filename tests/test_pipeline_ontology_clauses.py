"""Pipeline integration with ontology pack (default)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.extractors.registry import ExtractorRegistry
from zataone.policy_engine.corpus.ontology_loader import resolve_ontology_root


def _mock_extractors(self):
    from zataone.extractors.text_extractor import TextExtractor

    self._extractor_registry = ExtractorRegistry()
    self._extractor_registry.register(TextExtractor())


@pytest.mark.skipif(resolve_ontology_root() is None, reason="ontology/ not found")
def test_pipeline_loads_ontology_pack_by_default(monkeypatch):
    monkeypatch.delenv("ZATAONE_LEGACY_META_POLICY", raising=False)
    monkeypatch.setenv("ZATAONE_ONTOLOGY_PACK", "1")
    monkeypatch.setenv("ZATAONE_PIPELINE_ADVISORY", "0")
    monkeypatch.setenv("ZATAONE_POLICY_ENGINE_ENABLED", "0")

    from zataone.core.pipeline import CompliancePipeline

    with patch.object(CompliancePipeline, "_load_domain_extractors", _mock_extractors):
        pipe = CompliancePipeline(domain="ad_compliance", jurisdiction="US")

    pack = pipe._policy_pack
    assert pack is not None
    assert pack.id.startswith("ontology_")
    assert len(pack.clauses) >= 100
    assert len(pack.rules) >= 50
