"""Virality Index: scoring, schema tolerance, and concurrent pipeline join."""

import json
import os
import time
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

import zataone.integrations.gemini as gemini_mod
from zataone.core.pipeline_run import document_text, start_virality_review
from zataone.schemas.virality_review import (
    DIMENSION_NAMES,
    DIMENSION_WEIGHTS,
    ViralityDiagnostics,
    ViralityDimensions,
    ViralityReviewV2,
    compute_virality_index,
    diagnostic_flags,
    virality_band,
    wrap_stored_virality,
)
from zataone.virality.library import load_viral_patterns
from zataone.services.virality_review_service import (
    annotate_compliance_conflicts,
    run_virality_in_memory,
    score_virality_offline,
    virality_review_enabled,
)


@pytest.fixture(autouse=True)
def _no_llm(monkeypatch):
    """Keep every test on the deterministic heuristic path."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "0")


def test_weights_are_uniform_and_sum_to_one():
    assert len(DIMENSION_NAMES) == 7
    assert round(sum(DIMENSION_WEIGHTS.values()), 6) == 1.0
    assert len(set(DIMENSION_WEIGHTS.values())) == 1, "weights must stay uniform until fitted"


def test_retired_dimensions_are_gone():
    """interestingness was circular, excitement became arousal, clarity is a diagnostic."""
    for retired in ("interestingness", "excitement", "informativeness", "clarity"):
        assert retired not in DIMENSION_NAMES


def test_compute_virality_index_bounds():
    top = ViralityDimensions(**{k: 100 for k in DIMENSION_NAMES})
    bottom = ViralityDimensions(**{k: 0 for k in DIMENSION_NAMES})
    assert compute_virality_index(top) == 100
    assert compute_virality_index(bottom) == 0


def test_clarity_is_a_diagnostic_not_a_scored_dimension():
    """Clarity must not move the index; it is reported and flagged only."""
    dims = ViralityDimensions(**{k: 50 for k in DIMENSION_NAMES})
    clear = ViralityReviewV2(dimensions=dims, diagnostics=ViralityDiagnostics(clarity=95))
    muddy = ViralityReviewV2(dimensions=dims, diagnostics=ViralityDiagnostics(clarity=5))
    assert compute_virality_index(clear.dimensions) == compute_virality_index(muddy.dimensions)
    assert diagnostic_flags(muddy.diagnostics) != []
    assert diagnostic_flags(clear.diagnostics) == []


def test_brand_prominence_flags_as_negative_signal():
    flags = diagnostic_flags(ViralityDiagnostics(clarity=80, brand_prominence=90))
    assert any("reduce sharing" in f for f in flags)


def test_arousal_covers_negative_valence():
    """Anger/anxiety wording must raise arousal, not just upbeat wording."""
    anxious = score_virality_offline("Warning: this common mistake is costing you money.")
    calm = score_virality_offline("We hope you have a pleasant and restful afternoon.")
    assert anxious["dimensions"]["arousal"] > calm["dimensions"]["arousal"]


def test_short_punchy_copy_scores_clearer_than_rambling():
    short = score_virality_offline("Stop doing cardio to lose fat.")
    long_copy = score_virality_offline(
        "We would like to take a moment to tell you about our new product line which "
        "has many features that our team has worked very hard on over several quarters "
        "and we hope you will consider trying it at some point soon."
    )
    assert short["diagnostics"]["clarity"] > long_copy["diagnostics"]["clarity"]


def test_offline_score_shape():
    out = score_virality_offline("What if your ad spend actually paid you back?")
    assert out["schema_version"] == "2.0"
    assert out["weights_source"] == "uniform_prior"
    assert 0 <= out["virality_index"] <= 100
    assert out["scored_by"] == "heuristic"
    assert 1 <= len(out["suggestions"]) <= 3
    assert set(out["dimensions"]) == set(DIMENSION_NAMES)
    assert set(out["diagnostics"]) == {"clarity", "brand_prominence"}


def test_library_tags_use_the_scored_vocabulary():
    """The library and the score must share one vocabulary, and cover every dimension."""
    tags = {t for p in load_viral_patterns() for t in (p.get("tags") or [])}
    assert tags, "pattern library failed to load"
    assert tags <= set(DIMENSION_NAMES), f"off-vocabulary tags: {tags - set(DIMENSION_NAMES)}"
    assert tags == set(DIMENSION_NAMES), f"dimensions with no example pattern: {set(DIMENSION_NAMES) - tags}"


def test_schema_tolerates_bare_string_and_overlong_lists():
    m = ViralityReviewV2(
        dimensions=ViralityDimensions(**{k: 50 for k in DIMENSION_NAMES}),
        suggestions=["a", "b", "c", "d", "e", "f", "g"],
        compliance_conflicts="one note",
        pattern_match_strength="VERY STRONG",
    )
    assert len(m.suggestions) == 5
    assert m.compliance_conflicts == ["one note"]
    assert m.pattern_match_strength == "none"


def test_missing_diagnostics_do_not_break_validation():
    m = ViralityReviewV2(dimensions=ViralityDimensions(**{k: 50 for k in DIMENSION_NAMES}))
    assert m.diagnostics.clarity == 50
    assert m.diagnostics.brand_prominence == 0


def test_annotate_compliance_conflicts_is_idempotent():
    stored = score_virality_offline("Clinically proven to cure hair loss.")
    violations = [{"rule_id": "r1", "evidence_data": {"matched_text": "clinically proven"}}]
    annotate_compliance_conflicts(stored, violations=violations, compliance_status="NON_COMPLIANT")
    first = list(stored["compliance_conflicts"])
    annotate_compliance_conflicts(stored, violations=violations, compliance_status="NON_COMPLIANT")
    assert stored["compliance_conflicts"] == first
    assert any("clinically proven" in c for c in first)
    assert stored["compliance_status_at_scoring"] == "NON_COMPLIANT"


def test_virality_review_enabled_env(monkeypatch):
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "0")
    assert virality_review_enabled() is False
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    assert virality_review_enabled() is True


def test_virality_is_off_until_explicitly_enabled(monkeypatch):
    """
    A Gemini key must NOT imply consent to score creatives for shareability.

    Compliance review and virality scoring are two processing purposes. A deploy that
    carries a key for the first must not silently start sending copy out for the second.
    """
    monkeypatch.delenv("ZATAONE_VIRALITY_REVIEW", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setenv("GOOGLE_API_KEY", "k")
    assert virality_review_enabled() is False


def _bundle(status="COMPLIANT", violations=None):
    return {
        "verdict": {"status": status, "violations": violations or [], "metadata": {}},
        "violations_raw": violations or [],
    }


def test_start_virality_review_skips_without_text(monkeypatch):
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    assert start_virality_review(asset=SimpleNamespace(content=None), asset_id=None) is None


def test_start_virality_review_skips_when_disabled():
    assert start_virality_review(asset=SimpleNamespace(content="hi"), asset_id=None) is None


def test_image_asset_scores_on_extracted_vlm_text(monkeypatch):
    """An image has no asset.content, so it must score on the VLM/OCR document text."""
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    seen: dict[str, Any] = {}

    def _capture(**kwargs):
        seen.update(kwargs)
        return {"virality_index": 61}

    monkeypatch.setattr("zataone.services.virality_review_service.run_virality_in_memory", _capture)

    task = start_virality_review(
        asset=SimpleNamespace(content=None),
        asset_id=None,
        extracted_text="Every morning, before the coffee kicks in.",
    )
    assert task is not None
    assert task.join(_bundle())["virality_index"] == 61
    assert seen["text"] == "Every morning, before the coffee kicks in."


def test_asset_content_wins_over_extracted_text(monkeypatch):
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        "zataone.services.virality_review_service.run_virality_in_memory",
        lambda **kw: seen.update(kw) or {"virality_index": 5},
    )

    task = start_virality_review(
        asset=SimpleNamespace(content="the real ad copy"),
        asset_id=None,
        extracted_text="stale ocr text",
    )
    task.join(_bundle())
    assert seen["text"] == "the real ad copy"


def test_speculative_attempt_stays_quiet_until_extraction(monkeypatch):
    """
    The pre-extraction call for an image must not report a skip; only the post-extraction
    attempt knows whether any copy exists, so the UI never sees a spurious 'skipped'.
    """
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    updates: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "zataone.core.pipeline_run.progress_update",
        lambda asset_id, **kw: updates.append(kw),
    )
    asset = SimpleNamespace(content=None)
    aid = str(uuid.uuid4())

    assert start_virality_review(asset=asset, asset_id=aid) is None
    assert updates == []

    assert start_virality_review(asset=asset, asset_id=aid, extracted_text="") is None
    assert updates == [{"virality": "skipped", "virality_skipped_reason": "no_copy_found"}]


def _llm_payload(**overrides) -> str:
    body = {
        "schema_version": "2.0",
        "dimensions": {k: 60 for k in DIMENSION_NAMES},
        "diagnostics": {"clarity": 70, "brand_prominence": 10},
        "closest_pattern_id": "curiosity_gap",
        "closest_pattern_name": "Curiosity gap hook",
        "pattern_match_strength": "moderate",
        "suggestions": ["Novelty: sharpen the hook."],
        "summary": "Decent hook.",
        "compliance_conflicts": [],
    }
    body.update(overrides)
    return json.dumps(body)


def test_gemini_output_is_actually_parsed(monkeypatch):
    """
    Regression: _parse_json referenced the retired V1 schema, so every Gemini response
    raised NameError and silently degraded to the heuristic.
    """
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    monkeypatch.setattr(gemini_mod, "gemini_text_chat", lambda *a, **k: _llm_payload())

    out = run_virality_in_memory(text="Stop doing cardio to lose fat.")
    assert out["scored_by"] == "gemini", "LLM read was discarded"
    assert out["virality_index"] == 60
    assert out["closest_pattern_name"] == "Curiosity gap hook"


def test_gemini_output_survives_fences_comments_and_trailing_commas(monkeypatch):
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    messy = (
        "Here is the score:\n```json\n"
        + _llm_payload().rstrip("}")
        + ', "note": "see https://example.com/x" // trailing comment\n}\n```'
    )
    monkeypatch.setattr(gemini_mod, "gemini_text_chat", lambda *a, **k: messy)

    out = run_virality_in_memory(text="Stop doing cardio.")
    assert out["scored_by"] == "gemini"
    assert out["virality_index"] == 60


def test_unparseable_llm_output_falls_back_to_heuristic(monkeypatch):
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    monkeypatch.setattr(gemini_mod, "gemini_text_chat", lambda *a, **k: "not json at all")

    out = run_virality_in_memory(text="Stop doing cardio.")
    assert out["scored_by"] == "heuristic"
    assert 0 <= out["virality_index"] <= 100


def test_document_text_reads_vlm_normalized_text():
    verdict = {"metadata": {"document": {"normalized_text": "  a bold claim  "}}}
    assert document_text(verdict) == "a bold claim"
    assert document_text({"metadata": {}}) == ""
    assert document_text({"metadata": {"document": "not-a-dict"}}) == ""
    assert document_text(None) == ""


def test_document_text_prefers_vlm_structured_packet():
    """Score the VLM's reading of the creative, not a raw JSON dump of the packet."""
    verdict = {"metadata": {"document": {"normalized_text": '{"is_advertisement": false}'}}}
    vlm = {
        "structured": {
            "is_advertisement": True,
            "ocr_text": "Join 2.4M people who switched this week",
            "ad_claims_text": "Switch today",
            "scene_description": "A bold headline on a dark background",
            "objects": [],
        }
    }
    text = document_text(verdict, vlm_status=vlm)
    assert "Join 2.4M people" in text
    assert "Switch today" in text
    assert '{"is_advertisement"' not in text


def test_extracted_image_score_is_waited_on(monkeypatch):
    """Image scoring starts late; on Cloud Run a deferred write is dropped, so we wait."""
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    monkeypatch.setenv("ZATAONE_VIRALITY_EXTRACTED_TIMEOUT_MS", "2000")

    def _slow(**_kwargs):
        time.sleep(0.2)
        return {"virality_index": 44}

    monkeypatch.setattr("zataone.services.virality_review_service.run_virality_in_memory", _slow)
    task = start_virality_review(
        asset=SimpleNamespace(content=None),
        asset_id=None,
        extracted_text="Visible text: a bold claim",
    )
    stored = task.join(_bundle())
    assert stored is not None
    assert stored["virality_index"] == 44


def test_virality_runs_concurrently_with_compliance(monkeypatch):
    """The score must be ready by join time when compliance work took longer than it."""
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    monkeypatch.setattr(
        "zataone.services.virality_review_service.virality_review_enabled", lambda: False
    )

    task = start_virality_review(asset=SimpleNamespace(content="Only 47 spots left."), asset_id=None)
    assert task is not None
    time.sleep(0.05)  # stand-in for the compliance path

    bundle = _bundle(
        status="NON_COMPLIANT",
        violations=[{"rule_id": "r1", "evidence_data": {"matched_text": "only 47 spots"}}],
    )
    stored = task.join(bundle)
    assert stored is not None
    assert bundle["verdict"]["virality_index"] is stored
    assert bundle["verdict"]["metadata"]["virality_review"] is True
    assert any("only 47 spots" in c for c in stored["compliance_conflicts"])


def test_join_deadline_does_not_block_pipeline(monkeypatch):
    """A slow virality call is abandoned at the deadline instead of adding latency."""
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    monkeypatch.setenv("ZATAONE_VIRALITY_TIMEOUT_MS", "50")

    def _slow(**_kwargs):
        time.sleep(5)
        return {"virality_index": 99}

    monkeypatch.setattr("zataone.services.virality_review_service.run_virality_in_memory", _slow)

    task = start_virality_review(asset=SimpleNamespace(content="slow one"), asset_id=None)
    assert task is not None
    bundle = _bundle()
    t0 = time.perf_counter()
    assert task.join(bundle) is None
    elapsed_ms = (time.perf_counter() - t0) * 1000

    assert elapsed_ms < 500
    assert "virality_index" not in bundle["verdict"]
    assert bundle["verdict"]["metadata"]["virality_pending"] is True


def test_late_score_is_persisted_instead_of_waited_on(monkeypatch):
    """On timeout the worker's result still reaches the verdict row — no wasted LLM call."""
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")
    monkeypatch.setenv("ZATAONE_VIRALITY_TIMEOUT_MS", "20")

    def _slow(**_kwargs):
        time.sleep(0.1)
        return {"virality_index": 77}

    monkeypatch.setattr("zataone.services.virality_review_service.run_virality_in_memory", _slow)

    persisted: dict[str, Any] = {}
    monkeypatch.setattr(
        "zataone.core.pipeline_run._persist_late_virality",
        lambda asset_id, stored: persisted.update(asset_id=asset_id, stored=stored) or True,
    )

    asset_id = str(uuid.uuid4())
    task = start_virality_review(asset=SimpleNamespace(content="slow one"), asset_id=asset_id)
    assert task.join(_bundle()) is None

    for _ in range(50):
        if persisted:
            break
        time.sleep(0.02)
    assert persisted["asset_id"] == asset_id
    assert persisted["stored"]["virality_index"] == 77


def test_join_survives_worker_exception(monkeypatch):
    monkeypatch.setenv("ZATAONE_VIRALITY_REVIEW", "1")

    def _boom(**_kwargs):
        raise RuntimeError("gemini exploded")

    monkeypatch.setattr("zataone.services.virality_review_service.run_virality_in_memory", _boom)

    task = start_virality_review(asset=SimpleNamespace(content="boom"), asset_id=None)
    bundle = _bundle()
    assert task.join(bundle) is None
    assert "virality_index" not in bundle["verdict"]


def test_env_flag_isolation():
    assert os.environ.get("ZATAONE_VIRALITY_REVIEW") == "0"


def test_band_is_thirds_and_derived_on_store():
    """The band is the reportable form; it must be recomputed, never taken from input."""
    assert [virality_band(i) for i in (0, 33)] == ["low", "low"]
    assert [virality_band(i) for i in (34, 66)] == ["moderate", "moderate"]
    assert [virality_band(i) for i in (67, 100)] == ["high", "high"]

    review = ViralityReviewV2(
        dimensions=ViralityDimensions(
            arousal=90,
            social_currency=90,
            practical_value=90,
            story=90,
            novelty=90,
            triggers=90,
            public_observability=90,
        ),
        band="low",  # a lie on the way in
    )
    stored = wrap_stored_virality(review)
    assert stored["virality_index"] == 90
    assert stored["band"] == "high"  # corrected on the way out


def test_offline_score_is_labelled_as_heuristic():
    """An offline estimate must never be mistaken for a model score."""
    stored = score_virality_offline("Guaranteed results, today only")
    assert stored["scored_by"] == "heuristic"
    assert stored["band"] in ("low", "moderate", "high")
