"""
Unit tests for SemanticTextExtractor (ML sensor) and its fusion into the
policy engine via the embedding-by-regulation channel.

Uses an injected fake encoder so no model download is required.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

# Ensure src is first for correct zataone import
src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.extractors.semantic_text_extractor import SemanticTextExtractor
from zataone.policy_engine.engine import PolicyEngine


class _Rows(list):
    """Minimal matrix supporting .T and @ like normalized torch tensors."""

    @property
    def T(self):
        return _Rows(map(list, zip(*self)))

    def __matmul__(self, other):
        cols = list(map(list, zip(*other)))
        return [
            [sum(a * b for a, b in zip(row, col)) for col in cols]
            for row in self
        ]


def _fake_encoder(hot_word: str, hot_regulation_phrase: str):
    """Encoder mapping texts to 3D unit vectors: the hot concept (hot_word or
    the hot exemplar) -> axis 0, any other exemplar -> axis 1, everything
    else -> axis 2. Only hot text vs hot exemplar has similarity 1.0."""

    def encode(texts):
        rows = _Rows()
        for t in texts:
            lower = t.lower()
            if hot_word in lower or t == hot_regulation_phrase:
                rows.append([1.0, 0.0, 0.0])
            elif t in ("online casino betting win real money",):
                rows.append([0.0, 1.0, 0.0])
            else:
                rows.append([0.0, 0.0, 1.0])
        return rows

    return encode


def _extractor(encoder, threshold=0.5):
    return SemanticTextExtractor(
        similarity_threshold=threshold,
        exemplars={
            "medical_health_claims": ["cures diseases and heals your body"],
            "gambling": ["online casino betting win real money"],
        },
        encoder=encoder,
    )


def test_ignores_non_text_assets():
    ext = _extractor(_fake_encoder("slim", "cures diseases and heals your body"))
    assert ext.extract(SimpleNamespace(type="image", content="get slim fast")) == []


def test_short_text_produces_no_signals():
    ext = _extractor(_fake_encoder("slim", "cures diseases and heals your body"))
    assert ext.extract(SimpleNamespace(type="text", content="hi")) == []


def test_emits_signal_above_threshold_with_regulation_routing():
    encoder = _fake_encoder("slim", "cures diseases and heals your body")
    ext = _extractor(encoder)
    signals = ext.extract(
        SimpleNamespace(type="text", content="Get slim in days with our formula")
    )
    assert len(signals) == 1
    sig = signals[0]
    assert sig.signal_type == "semantic_similarity"
    assert sig.raw_data["type"] == "text_embedding_similarity"
    assert sig.raw_data["regulation"] == "medical_health_claims"
    assert sig.confidence > 0.5


def test_no_signal_below_threshold():
    encoder = _fake_encoder("slim", "cures diseases and heals your body")
    ext = _extractor(encoder)
    signals = ext.extract(
        SimpleNamespace(type="text", content="A perfectly ordinary chair for sale")
    )
    assert signals == []


def test_missing_model_degrades_gracefully():
    ext = SemanticTextExtractor(encoder=None, model_name="nonexistent/model-xyz")
    # Force the lazy loader path with a model that cannot load
    from zataone.extractors import semantic_text_extractor as mod

    old_state = dict(mod._model_state)
    mod._model_state.update({"checked": True, "encoder": None})
    try:
        assert ext.extract(SimpleNamespace(type="text", content="guaranteed results now")) == []
    finally:
        mod._model_state.update(old_state)


def test_policy_engine_fuses_text_similarity_as_supporting_evidence():
    """text_embedding_similarity signals attach as supporting evidence to a
    rule triggered deterministically (ML supports; the DSL decides)."""
    engine = PolicyEngine()
    engine.load_policy_pack(
        rules={
            "medical_health_claims": {
                "name": "Medical Health Claims",
                "prohibited_terms": ["miracle cure"],
                "severity": "HIGH",
            },
        },
        embedding_rule_map={"medical_health_claims": "medical_health_claims"},
    )

    text_signal = SimpleNamespace(
        signal_id="txt-001",
        signal_type="keyword",
        source_model="text_extractor",
        confidence=0.9,
        raw_data={"text": "This miracle cure heals everything", "type": "ocr_text"},
    )
    ml_signal = SimpleNamespace(
        signal_id="sem-001",
        signal_type="semantic_similarity",
        source_model="semantic_text_extractor",
        confidence=0.82,
        raw_data={
            "type": "text_embedding_similarity",
            "regulation": "medical_health_claims",
            "score": 0.82,
            "model": "sentence-transformers/all-MiniLM-L6-v2",
        },
    )

    violations = engine.evaluate([text_signal, ml_signal])

    det = [v for v in violations if v.signal_id == "txt-001"]
    sem = [v for v in violations if v.signal_id == "sem-001"]
    assert len(det) >= 1  # deterministic match triggered the rule
    assert len(sem) == 1  # ML similarity attached as supporting evidence
    assert sem[0].violation_type == "text_embedding_similarity"
    assert sem[0].rule_id == "medical_health_claims"
    assert sem[0].evidence_data["evidence_type"] == "text_embedding_similarity"


def test_policy_engine_ignores_ml_signal_without_deterministic_trigger():
    """ML similarity alone must not create a violation — deterministic rules
    are the only judge."""
    engine = PolicyEngine()
    engine.load_policy_pack(
        rules={
            "medical_health_claims": {
                "name": "Medical Health Claims",
                "prohibited_terms": ["miracle cure"],
                "severity": "HIGH",
            },
        },
        embedding_rule_map={"medical_health_claims": "medical_health_claims"},
    )
    ml_signal = SimpleNamespace(
        signal_id="sem-001",
        signal_type="semantic_similarity",
        source_model="semantic_text_extractor",
        confidence=0.82,
        raw_data={
            "type": "text_embedding_similarity",
            "regulation": "medical_health_claims",
            "score": 0.82,
            "model": "sentence-transformers/all-MiniLM-L6-v2",
        },
    )
    assert engine.evaluate([ml_signal]) == []
