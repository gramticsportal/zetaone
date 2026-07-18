"""Review workflow: queue-entry rules, feedback sanitization, ObjectStore, degraded extraction."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))


# ── review_state_for_verdict ─────────────────────────────────────────────────


def test_clean_deterministic_compliant_auto_clears():
    from zataone.services.review_service import review_state_for_verdict

    v = {
        "status": "COMPLIANT",
        "verdict": "likely_approved",
        "metadata": {"verdict_authority": "deterministic"},
    }
    assert review_state_for_verdict(v) is None


@pytest.mark.parametrize(
    "status,band",
    [
        ("REVIEW_REQUIRED", "borderline"),
        ("NON_COMPLIANT", "likely_rejected"),
        ("LIKELY_REJECTED", "likely_rejected"),
        ("PENDING_ADVISORY", "pending_advisory"),
    ],
)
def test_flagged_outcomes_enter_queue(status, band):
    from zataone.services.review_service import review_state_for_verdict

    v = {"status": status, "verdict": band, "metadata": {"verdict_authority": "deterministic"}}
    assert review_state_for_verdict(v) == "pending_review"


def test_degraded_extraction_enters_queue_even_when_compliant():
    from zataone.services.review_service import review_state_for_verdict

    v = {
        "status": "COMPLIANT",
        "verdict": "likely_approved",
        "metadata": {
            "verdict_authority": "deterministic",
            "degraded_extractors": {"ad_compliance_vision": "RuntimeError: model load failed"},
        },
    }
    assert review_state_for_verdict(v) == "pending_review"


def test_advisory_authority_cannot_auto_clear():
    from zataone.services.review_service import review_state_for_verdict

    v = {
        "status": "COMPLIANT",
        "verdict": "likely_approved",
        "metadata": {"verdict_authority": "advisory"},
    }
    assert review_state_for_verdict(v) == "pending_review"


# ── violation feedback sanitization ──────────────────────────────────────────


def test_feedback_sanitization_drops_invalid_assessments():
    from zataone.services.review_service import _sanitize_feedback

    out = _sanitize_feedback(
        [
            {"rule_id": "gambling", "assessment": "false_positive", "note": "demo casino, free to play"},
            {"rule_id": "tobacco", "assessment": "TRUE_POSITIVE"},
            {"rule_id": "bad", "assessment": "maybe"},
            "not-a-dict",
        ]
    )
    assert len(out) == 2
    assert out[0]["assessment"] == "false_positive"
    assert out[1]["assessment"] == "true_positive"


# ── ObjectStore (local backend) ──────────────────────────────────────────────


def test_object_store_local_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ZATAONE_OBJECT_STORE_DIR", str(tmp_path))
    monkeypatch.delenv("ZATAONE_OBJECT_STORE_BUCKET", raising=False)
    from zataone.storage.object_store import ObjectStore

    store = ObjectStore()
    uri = store.put(b"fake-image-bytes", "image/png")
    assert uri.startswith("file://")

    data, content_type = store.get(uri)
    assert data == b"fake-image-bytes"
    assert content_type == "image/png"

    # Idempotent: same content → same URI
    assert store.put(b"fake-image-bytes", "image/png") == uri
    assert store.exists(uri)
    assert not store.exists("file:///nowhere/aa/bb/deadbeef")


# ── degraded extraction propagation ─────────────────────────────────────────


def test_extractor_failure_is_reported():
    from zataone.core.pipeline_run import extract_signals_parallel

    ok = MagicMock()
    ok.extractor_id = "ok_ext"
    ok.extract.return_value = [{"x": 1}]

    boom = MagicMock()
    boom.extractor_id = "boom_ext"
    boom.extract.side_effect = RuntimeError("model load failed")

    with patch(
        "zataone.core.pipeline_run.pipeline_parallel_extractors_enabled", return_value=False
    ):
        signals, counts, failed = extract_signals_parallel(
            [ok, boom], SimpleNamespace(type="image")
        )
    assert len(signals) == 1
    assert counts == {"ok_ext": 1, "boom_ext": 0}
    assert "boom_ext" in failed
    assert "model load failed" in failed["boom_ext"]
