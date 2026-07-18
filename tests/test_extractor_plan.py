"""Extractor modality plan and flags."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.core.extractor_flags import embedding_enabled
from zataone.core.extractor_plan import select_extractors_for_asset


def _mock_ext(eid: str):
    m = MagicMock()
    m.extractor_id = eid
    return m


def test_text_asset_only_text_extractor(monkeypatch):
    monkeypatch.delenv("ZATAONE_ENABLE_EMBEDDING", raising=False)
    extractors = [
        _mock_ext("text_extractor"),
        _mock_ext("ad_compliance_ocr"),
        _mock_ext("ad_compliance_vision"),
        _mock_ext("ad_compliance_embedding"),
    ]
    asset = SimpleNamespace(type="text", content="hello")
    config = {"extractors": {"enabled": ["ocr", "vision"]}}
    selected = select_extractors_for_asset(extractors, asset, config)
    assert [e.extractor_id for e in selected] == ["text_extractor"]


def test_image_asset_ocr_vision_off_by_default(monkeypatch):
    """VLM-primary path: local OCR/DINO off unless explicitly enabled."""
    monkeypatch.delenv("ZATAONE_ENABLE_EMBEDDING", raising=False)
    monkeypatch.delenv("ZATAONE_ENABLE_OCR", raising=False)
    monkeypatch.delenv("ZATAONE_ENABLE_VISION", raising=False)
    extractors = [
        _mock_ext("text_extractor"),
        _mock_ext("ad_compliance_ocr"),
        _mock_ext("ad_compliance_vision"),
        _mock_ext("ad_compliance_embedding"),
    ]
    asset = SimpleNamespace(type="image", image_data=b"x")
    config = {"extractors": {"enabled": ["ocr", "vision"]}}
    selected = select_extractors_for_asset(extractors, asset, config)
    ids = {e.extractor_id for e in selected}
    assert "ad_compliance_ocr" not in ids
    assert "ad_compliance_vision" not in ids
    assert "ad_compliance_embedding" not in ids


def test_image_asset_ocr_vision_when_flags_on(monkeypatch):
    monkeypatch.setenv("ZATAONE_ENABLE_OCR", "1")
    monkeypatch.setenv("ZATAONE_ENABLE_VISION", "1")
    monkeypatch.delenv("ZATAONE_ENABLE_EMBEDDING", raising=False)
    extractors = [
        _mock_ext("ad_compliance_ocr"),
        _mock_ext("ad_compliance_vision"),
        _mock_ext("ad_compliance_embedding"),
    ]
    asset = SimpleNamespace(type="image", image_data=b"x")
    config = {"extractors": {"enabled": ["ocr", "vision"]}}
    selected = select_extractors_for_asset(extractors, asset, config)
    ids = {e.extractor_id for e in selected}
    assert "ad_compliance_ocr" in ids
    assert "ad_compliance_vision" in ids
    assert "ad_compliance_embedding" not in ids


def test_embedding_when_flag_on(monkeypatch):
    monkeypatch.setenv("ZATAONE_ENABLE_EMBEDDING", "true")
    monkeypatch.setenv("ZATAONE_ENABLE_OCR", "1")
    monkeypatch.setenv("ZATAONE_ENABLE_VISION", "1")
    assert embedding_enabled() is True
    extractors = [_mock_ext("ad_compliance_embedding")]
    asset = SimpleNamespace(type="image", image_data=b"x")
    config = {"extractors": {"enabled": ["embedding", "ocr", "vision"]}}
    selected = select_extractors_for_asset(extractors, asset, config)
    assert len(selected) == 1
