"""Fast pipeline path: parallel extractors mocked, no models."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))


def test_parallel_extractors_collects_signals():
    from zataone.core.pipeline_run import extract_signals_parallel

    def _slow_ext():
        m = MagicMock()
        m.extractor_id = "a"
        m.extract.return_value = [{"x": 1}]
        return m

    def _fast_ext():
        m = MagicMock()
        m.extractor_id = "b"
        m.extract.return_value = []
        return m

    with patch("zataone.core.pipeline_run.pipeline_parallel_extractors_enabled", return_value=True):
        signals, counts, failed = extract_signals_parallel([_slow_ext(), _fast_ext()], SimpleNamespace(type="text"))
    assert len(signals) == 1
    assert counts.get("a") == 1
    assert failed == {}


def test_pipeline_run_includes_metadata_flags(monkeypatch):
    monkeypatch.setenv("ZATAONE_PIPELINE_ADVISORY", "0")
    from zataone.core.pipeline import CompliancePipeline

    def mock_load_extractors(self):
        from zataone.extractors.registry import ExtractorRegistry
        from zataone.extractors.text_extractor import TextExtractor

        self._extractor_registry = ExtractorRegistry()
        self._extractor_registry.register(TextExtractor())
        self._domain_config = {"extractors": {"enabled": ["ocr", "vision"]}}

    fake_signal = SimpleNamespace(
        id="sig-1",
        extractor_id="text",
        signal_type="text",
        confidence=0.9,
        value={"text": "guaranteed instant cure"},
        raw_data={"text": "guaranteed instant cure"},
    )

    with patch.object(CompliancePipeline, "_load_domain_extractors", mock_load_extractors):
        with patch.object(CompliancePipeline, "_load_domain_policies"):
            with patch(
                "zataone.core.pipeline.extract_signals_parallel",
                return_value=([fake_signal], {"text": 1}),
            ):
                pipeline = CompliancePipeline(domain="ad_compliance")
                asset = {"content": "guaranteed instant cure", "type": "text"}
                result = pipeline.run(asset, persist=False)

    assert "verdict" in result
    meta = result.get("metadata") or {}
    assert meta.get("embedding_enabled") is False
    assert "extractor_counts" in meta or "pipeline_timing" in meta
