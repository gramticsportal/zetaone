"""Phase B hybrid engine tests (lexical + NLP BoW, no MiniLM download)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))


@pytest.fixture(autouse=True)
def _hybrid_bow(monkeypatch):
    monkeypatch.setenv("ZATAONE_HYBRID_ENGINE", "1")
    monkeypatch.setenv("ZATAONE_HYBRID_NLP", "1")
    monkeypatch.setenv("ZATAONE_HYBRID_NLP_BACKEND", "bow")
    monkeypatch.setenv("ZATAONE_HYBRID_NLP_THRESHOLD", "0.35")


def test_load_approved_packs():
    from zataone.policy_engine.hybrid.pack_loader import load_pattern_packs

    packs = load_pattern_packs(approved_only=True)
    assert len(packs) >= 40
    assert any(p.category_id == "misleading" for p in packs.values())


def test_lexical_hits_misleading_guarantee():
    from zataone.policy_engine.hybrid.engine import HybridEngine
    from zataone.schemas.document import DocumentSignal

    eng = HybridEngine()
    assert eng.pack_count >= 40
    doc = DocumentSignal(
        asset_id=None,
        modality="text",
        normalized_text="Guaranteed miracle overnight results 100% clinically proven!",
        spans=[],
        scene_descriptions=[],
        source_signal_ids=[],
        timeline=[],
        metadata={},
    )
    result = eng.evaluate_full([], document=doc, active_rule_ids=None)
    assert result.violations, "expected hybrid violations on exaggerated claims"
    assert any(v.evidence_data.get("hybrid") for v in result.violations)
    assert result.signals, "expected hybrid signals"
    matchers = {v.evidence_data.get("matcher") for v in result.violations}
    assert matchers & {"phrase", "regex", "term", "nlp_embedding"}


def test_academic_slide_does_not_fire_political_phrase():
    from zataone.policy_engine.hybrid.engine import HybridEngine
    from zataone.schemas.document import DocumentSignal

    eng = HybridEngine()
    doc = DocumentSignal(
        asset_id=None,
        modality="text",
        normalized_text=(
            "Approximation and estimation error. Underfitting. Overfitting. "
            "hypothesis class size. statistical learning theory. Feature extraction."
        ),
        spans=[],
        scene_descriptions=[],
        source_signal_ids=[],
        timeline=[],
        metadata={},
    )
    # Restrict shortlist to political packs only via fake rule ids that map to political
    political_rules = []
    for cid, pack in eng._packs.items():
        if pack.category_id == "political":
            political_rules.extend(pack.source_rule_ids)
    result = eng.evaluate_full([], document=doc, active_rule_ids=set(political_rules) or None)
    political_hits = [
        v
        for v in result.violations
        if (v.evidence_data or {}).get("category_id") == "political"
        and (v.evidence_data or {}).get("matcher") in ("phrase", "regex")
    ]
    assert political_hits == [], f"unexpected political hits: {political_hits}"


def test_vision_respects_min_confidence():
    from zataone.policy_engine.hybrid.lexical import match_vision
    from zataone.policy_engine.hybrid.pack_loader import PatternPack

    pack = PatternPack(
        canonical_id="political.test",
        category_id="political",
        severity="high",
        review_status="approved",
        vision_labels=["campaign poster"],
        vision_min_confidence=0.65,
    )
    weak = SimpleNamespace(
        signal_id="v1",
        signal_type="vision_object",
        confidence=0.40,
        raw_data={"label": "campaign poster", "confidence": 0.40},
    )
    strong = SimpleNamespace(
        signal_id="v2",
        signal_type="vision_object",
        confidence=0.80,
        raw_data={"label": "campaign poster", "confidence": 0.80},
    )
    assert match_vision([weak], pack) == []
    assert len(match_vision([strong], pack)) == 1


def test_hybrid_flag_off_uses_policy_engine(monkeypatch):
    monkeypatch.setenv("ZATAONE_HYBRID_ENGINE", "0")
    monkeypatch.setenv("ZATAONE_POLICY_ENGINE_ENABLED", "0")
    from zataone.policy_engine.hybrid.flags import hybrid_engine_enabled

    assert hybrid_engine_enabled() is False


def test_nlp_bow_scores_health_prototype():
    from zataone.policy_engine.hybrid.nlp import HybridNLPScorer
    from zataone.policy_engine.hybrid.pack_loader import PatternPack

    scorer = HybridNLPScorer()
    assert scorer.backend == "bow"
    pack = PatternPack(
        canonical_id="health.disease_cure_treatment_claims",
        category_id="health",
        severity="high",
        review_status="approved",
        embedding_prototypes=[
            "Claims to cure heal eliminate incurable disease or terminal illness"
        ],
        requires_context_terms=["disease", "cancer"],
    )
    hit = scorer.score_pack(
        "This miracle pill cures cancer and eliminates diabetes overnight",
        pack,
    )
    assert hit is not None
    assert hit["score"] >= 0.22
    assert hit["backend"] == "bow"
