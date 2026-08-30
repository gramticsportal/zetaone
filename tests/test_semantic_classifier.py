# -*- coding: utf-8 -*-
"""The learned tier: deterministic training, and it must never decide a verdict."""

from __future__ import annotations

import numpy as np
import pytest

from zataone.policy_engine.ml.semantic_classifier import (
    STRUCTURAL_FEATURES,
    SemanticClassifier,
    TrainedModel,
    build_vocabulary,
    featurize,
    train_logistic,
)

TEXTS = [
    "guaranteed cure for cancer in seven days",
    "miracle weight loss with zero effort",
    "make $10,000 a week guaranteed passive income",
    "risk free investment with guaranteed returns",
    "a daily multivitamin to help support overall wellness",
    "results may vary and are not typical for most users",
    "our app can help you save money by automating transfers",
    "consult your doctor before starting any supplement",
]
LABELS = np.array([1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0])


def fit():
    vocab = build_vocabulary(TEXTS, min_df=1)
    X = featurize(TEXTS, vocab)
    w, b, hist = train_logistic(X, LABELS, iterations=200)
    return vocab, X, w, b, hist


def test_training_is_reproducible_bit_for_bit() -> None:
    """Same input, same weights. This is the contract that lets a model pin to a corpus."""
    _, _, w1, b1, _ = fit()
    _, _, w2, b2, _ = fit()
    assert np.array_equal(w1, w2)
    assert b1 == b2


def test_vocabulary_order_is_stable() -> None:
    assert build_vocabulary(TEXTS, min_df=1) == build_vocabulary(list(TEXTS), min_df=1)


def test_loss_decreases() -> None:
    _, _, _, _, hist = fit()
    assert hist[-1] < hist[0]


def test_it_separates_the_training_data() -> None:
    vocab, X, w, b, _ = fit()
    model = TrainedModel(weights=w, bias=b, vocab=vocab)
    p = model.predict_proba(TEXTS)
    assert p[:4].min() > p[4:].max(), "violations should score above compliant copy"


def test_featurizer_shape_and_normalisation() -> None:
    vocab = build_vocabulary(TEXTS, min_df=1)
    X = featurize(TEXTS, vocab)
    assert X.shape == (len(TEXTS), len(vocab) + len(STRUCTURAL_FEATURES))
    ngram_norms = np.linalg.norm(X[:, : len(vocab)], axis=1)
    assert np.allclose(ngram_norms, 1.0, atol=1e-5)


def test_structural_features_fire() -> None:
    vocab = build_vocabulary(TEXTS, min_df=1)
    row = featurize(["Act now! Save $500 — 100% guaranteed"], vocab)[0]
    flags = dict(zip(STRUCTURAL_FEATURES, row[len(vocab) :]))
    assert flags["has_currency"] == 1.0
    assert flags["has_percent"] == 1.0
    assert flags["has_urgency"] == 1.0
    assert flags["has_absolute_qualifier"] == 1.0


def test_explain_returns_contributing_features() -> None:
    vocab, X, w, b, _ = fit()
    model = TrainedModel(weights=w, bias=b, vocab=vocab)
    top = model.explain("guaranteed cure for cancer", top_k=5)
    assert top and all(isinstance(name, str) for name, _ in top)


def test_round_trip_through_disk(tmp_path) -> None:
    vocab, X, w, b, _ = fit()
    model = TrainedModel(weights=w, bias=b, vocab=vocab, threshold=0.42, meta={"trained_on": "train"})
    path = tmp_path / "m.npz"
    model.save(path)
    loaded = TrainedModel.load(path)
    assert loaded.threshold == 0.42
    assert loaded.meta["trained_on"] == "train"
    assert np.allclose(loaded.predict_proba(TEXTS), model.predict_proba(TEXTS))


def test_missing_artifact_degrades_to_silence(tmp_path) -> None:
    clf = SemanticClassifier(model_path=tmp_path / "absent.npz")
    assert not clf.available
    assert clf.score("guaranteed cure for cancer") is None


def test_sigmoid_is_stable_at_extremes() -> None:
    from zataone.policy_engine.ml.semantic_classifier import _sigmoid

    out = _sigmoid(np.array([-1e4, 0.0, 1e4]))
    assert not np.isnan(out).any()
    assert 0.0 <= out.min() and out.max() <= 1.0


@pytest.mark.parametrize("text", ["", "   "])
def test_empty_text_scores_none(text: str) -> None:
    vocab, X, w, b, _ = fit()
    model = TrainedModel(weights=w, bias=b, vocab=vocab)
    clf = SemanticClassifier.__new__(SemanticClassifier)
    clf._model = model
    assert clf.score(text) is None
