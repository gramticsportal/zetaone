"""Pipeline full vs fast mode (no live models)."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))


def _mock_pipeline():
    from zataone.core.pipeline import CompliancePipeline

    def mock_load_extractors(self):
        from zataone.extractors.registry import ExtractorRegistry
        from zataone.extractors.text_extractor import TextExtractor

        self._extractor_registry = ExtractorRegistry()
        self._extractor_registry.register(TextExtractor())
        self._domain_config = {"extractors": {"enabled": ["ocr", "vision"]}}

    return mock_load_extractors


def test_fast_mode_skips_extractors(monkeypatch):
    monkeypatch.setenv("ZATAONE_PIPELINE_ADVISORY", "0")
    from zataone.core.pipeline import CompliancePipeline

    with patch.object(CompliancePipeline, "_load_domain_extractors", _mock_pipeline()):
        with patch.object(CompliancePipeline, "_load_domain_policies"):
            pipeline = CompliancePipeline(domain="ad_compliance")
            asset = SimpleNamespace(
                content="guaranteed instant cure",
                type="text",
                image_data=None,
            )
            result = pipeline.run(asset, persist=False, pipeline_mode="fast")

    meta = result.get("metadata") or {}
    assert meta.get("pipeline_mode") == "fast"
    assert meta.get("fast_mode_no_extractors") is True
    assert meta.get("policy_engine_ran") is False
    assert meta.get("verdict_authority") == "advisory"


def test_resolve_pipeline_mode_header_overrides_env(monkeypatch):
    monkeypatch.setenv("ZATAONE_PIPELINE_MODE", "full")
    from zataone.core.pipeline import resolve_pipeline_mode

    assert resolve_pipeline_mode("fast") == "fast"
    assert resolve_pipeline_mode(None) == "full"


def test_full_mode_runs_extractors(monkeypatch):
    monkeypatch.setenv("ZATAONE_PIPELINE_ADVISORY", "0")
    from zataone.core.pipeline import CompliancePipeline

    with patch.object(CompliancePipeline, "_load_domain_extractors", _mock_pipeline()):
        with patch.object(CompliancePipeline, "_load_domain_policies"):
            pipeline = CompliancePipeline(domain="ad_compliance")
            asset = {"content": "test ad copy", "type": "text"}
            result = pipeline.run(asset, persist=False, pipeline_mode="full")

    meta = result.get("metadata") or {}
    assert meta.get("pipeline_mode") == "full"
    assert "fast_mode_no_extractors" not in meta
    assert meta.get("policy_engine_ran") is False


def test_full_mode_policy_engine_when_enabled(monkeypatch):
    monkeypatch.setenv("ZATAONE_PIPELINE_ADVISORY", "0")
    monkeypatch.setenv("ZATAONE_POLICY_ENGINE_ENABLED", "1")
    from zataone.core.pipeline import CompliancePipeline

    with patch.object(CompliancePipeline, "_load_domain_extractors", _mock_pipeline()):
        with patch.object(CompliancePipeline, "_load_domain_policies"):
            pipeline = CompliancePipeline(domain="ad_compliance")
            asset = {"content": "guaranteed instant cure 100%", "type": "text"}
            result = pipeline.run(asset, persist=False, pipeline_mode="full")

    meta = result.get("metadata") or {}
    assert meta.get("policy_engine_ran") is True
