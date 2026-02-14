"""
Integration test for database persistence.
Requires PostgreSQL at DATABASE_URL (default: postgresql://localhost:5432/zetaone).
Run with: pytest tests/test_persistence.py -v -s
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

# Ensure src is first for correct zetaone import
src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

import pytest

from zetaone.core.pipeline import CompliancePipeline
from zetaone.storage import database as db
from zetaone.storage.database import create_all_tables, SessionLocal, get_session_factory
from zetaone.models.asset import Asset
from zetaone.models.signal import Signal
from zetaone.models.verdict import Verdict


def test_persistence():
    """Run pipeline and verify compliance graph is persisted to database."""
    from zetaone.extractors.registry import ExtractorRegistry

    try:
        create_all_tables()
    except Exception as e:
        pytest.skip(f"Database not available: {e}")

    # Mock extractors to avoid loading external models (pytesseract, etc.)
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
        pipeline = CompliancePipeline(domain="ad_compliance")

        asset = SimpleNamespace(
            asset_id="persist-test",
            content="Guaranteed instant cure",
            type="text",
        )

        result = pipeline.run(asset)

    session = db.SessionLocal()

    try:
        assert session.query(Asset).count() >= 1
        assert session.query(Verdict).count() >= 1

        verdict = session.query(Verdict).order_by(Verdict.created_at.desc()).first()
        if verdict:
            print(verdict.result)
    finally:
        session.close()
