"""
Simple integration test for ZetaOne CompliancePipeline.
Does not depend on external models (mocks extractor loading).
"""

import sys
from pathlib import Path

# Ensure src is first for correct zetaone import
src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

import pytest
from unittest.mock import patch, MagicMock


def test_zetaone_pipeline_run():
    """Run CompliancePipeline with minimal asset and assert result structure."""
    from zetaone.core.pipeline import CompliancePipeline
    from zetaone.extractors.registry import ExtractorRegistry

    # Create mock extractors that return empty signals (no model inference)
    def make_mock_extractor(extractor_id):
        ext = MagicMock()
        ext.extractor_id = extractor_id
        ext.version = "1.0"
        ext.extract.return_value = []
        return ext

    mock_extractors = [
        make_mock_extractor("ad_compliance_ocr"),
        make_mock_extractor("ad_compliance_vision"),
        make_mock_extractor("ad_compliance_embedding"),
        make_mock_extractor("ad_compliance_vlm"),
    ]

    def mock_load_extractors(self):
        self._extractor_registry = ExtractorRegistry()
        for ext in mock_extractors:
            self._extractor_registry.register(ext)

    with patch.object(
        CompliancePipeline,
        "_load_domain_extractors",
        mock_load_extractors,
    ):
        asset = {
            "asset_id": "test-1",
            "content": "This product guarantees instant results",
            "type": "text",
        }

        pipeline = CompliancePipeline(domain="ad_compliance")
        result = pipeline.run(asset, persist=False)

    print(result)

    assert "verdict" in result
    assert "risk_score" in result
    assert "violations" in result
    assert "signals" in result
