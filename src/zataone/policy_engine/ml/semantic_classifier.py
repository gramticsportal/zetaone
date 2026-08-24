# zataone semantic classifier — the learned tier, as a sensor

"""A small linear model over lexical and structural features, trained on the train split.

Why linear, and why numpy rather than a transformer:

**It has to be auditable.** This system's product is a defensible decision. A model whose
contribution to a verdict cannot be read off as "these words, this much weight" would
undermine the evidence chain the rest of the engine exists to protect. Every coefficient
here is inspectable, and `explain()` returns the exact features that moved a score.

**It has to be reproducible.** Training is deterministic — zero initialisation, full-batch
gradient descent, a fixed iteration count, a vocabulary built by sorting. Same corpus,
same split, same weights, bit for bit. That is the same contract the deterministic tier
offers, and it is what lets a model version be pinned to a corpus version.

**It has to run offline.** The artifact is one `.npz`. No torch, no transformers, no
download, no GPU. That keeps the air-gapped deployment story intact.

**It never decides.** `SemanticClassifier` emits a score. The verdict stays with the
deterministic engine, exactly like the VLM and OCR sensors.

The honest limitation: this cannot separate a minimal pair on vocabulary alone, because
the pairs were built to share vocabulary. It is expected to help where the deterministic
tier has no trigger at all — paraphrase and implication — and to add nothing where the
qualifier gate is already doing the work. Measure it on `dev`, never on `test`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np

# Structural features appended after the n-gram block. Named so `explain()` can report
# them, and kept few: each one is a claim about what matters, not a free parameter.
STRUCTURAL_FEATURES = (
    "has_percent",
    "has_currency",
    "has_number",
    "has_superlative",
    "has_absolute_qualifier",
    "has_hedge",
    "has_urgency",
    "has_second_person",
    "is_short",
    "ends_exclaim",
)

_WORD_RE = re.compile(r"[a-z0-9$%]+")
_SUPERLATIVE_RE = re.compile(r"(?<![a-z])(best|top|#\s?1|no\.?\s?1|fastest|strongest|safest|cheapest|leading|ultimate|most\s+\w+est)(?![a-z])")
_ABSOLUTE_RE = re.compile(r"(?<![a-z])(guaranteed?|always|never|100%|totally|completely|permanently|instantly|zero|any(?:one|body))(?![a-z])")
_HEDGE_RE = re.compile(r"(?<![a-z])(may|might|can help|could|designed to|intended to|helps?\s+support|typical|results vary)(?![a-z])")
_URGENCY_RE = re.compile(r"(?<![a-z])(act now|limited time|hurry|today only|last chance|don'?t miss|expires?)(?![a-z])")
_SECOND_PERSON_RE = re.compile(r"(?<![a-z])(you|your|you'?re)(?![a-z])")


def _tokens(text: str) -> list[str]:
    return _WORD_RE.findall((text or "").lower())


def _ngram_keys(text: str) -> list[str]:
    """Word unigrams and bigrams, plus character 4-grams for morphology and misspelling."""
    toks = _tokens(text)
    keys = ["w:" + t for t in toks]
    keys += ["b:%s_%s" % (a, b) for a, b in zip(toks, toks[1:])]
    compact = " ".join(toks)
    keys += ["c:" + compact[i : i + 4] for i in range(max(0, len(compact) - 3))]
    return keys


def _structural(text: str) -> list[float]:
    low = (text or "").lower()
    return [
        1.0 if "%" in low else 0.0,
        1.0 if "$" in low else 0.0,
        1.0 if re.search(r"\d", low) else 0.0,
        1.0 if _SUPERLATIVE_RE.search(low) else 0.0,
        1.0 if _ABSOLUTE_RE.search(low) else 0.0,
        1.0 if _HEDGE_RE.search(low) else 0.0,
        1.0 if _URGENCY_RE.search(low) else 0.0,
        1.0 if _SECOND_PERSON_RE.search(low) else 0.0,
        1.0 if len(low) < 40 else 0.0,
        1.0 if low.rstrip().endswith("!") else 0.0,
    ]


def build_vocabulary(texts: Sequence[str], *, min_df: int = 2, max_features: int = 20000) -> dict[str, int]:
    """Deterministic vocabulary: document frequency, then sorted for a stable tie-break."""
    df: dict[str, int] = {}
    for text in texts:
        for key in set(_ngram_keys(text)):
            df[key] = df.get(key, 0) + 1
    kept = [(k, c) for k, c in df.items() if c >= min_df]
    # Sort by frequency desc then key asc: ties resolve identically on every machine.
    kept.sort(key=lambda kv: (-kv[1], kv[0]))
    return {k: i for i, (k, _) in enumerate(kept[:max_features])}


def featurize(texts: Sequence[str], vocab: dict[str, int]) -> np.ndarray:
    """Rows of L2-normalised n-gram counts with structural flags appended."""
    n_ngram = len(vocab)
    out = np.zeros((len(texts), n_ngram + len(STRUCTURAL_FEATURES)), dtype=np.float32)
    for row, text in enumerate(texts):
        for key in _ngram_keys(text):
            idx = vocab.get(key)
            if idx is not None:
                out[row, idx] += 1.0
        norm = float(np.linalg.norm(out[row, :n_ngram]))
        if norm > 0:
            out[row, :n_ngram] /= norm
        out[row, n_ngram:] = _structural(text)
    return out


@dataclass
class TrainedModel:
    weights: np.ndarray
    bias: float
    vocab: dict[str, int]
    threshold: float = 0.5
    meta: dict | None = None

    def predict_proba(self, texts: Sequence[str]) -> np.ndarray:
        X = featurize(texts, self.vocab)
        return _sigmoid(X @ self.weights + self.bias)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            path,
            weights=self.weights,
            bias=np.array([self.bias], dtype=np.float64),
            threshold=np.array([self.threshold], dtype=np.float64),
            vocab_keys=np.array(list(self.vocab.keys()), dtype=object),
            vocab_idx=np.array(list(self.vocab.values()), dtype=np.int32),
            meta=np.array([json.dumps(self.meta or {})], dtype=object),
        )

    @classmethod
    def load(cls, path: Path) -> "TrainedModel":
        data = np.load(path, allow_pickle=True)
        vocab = {str(k): int(i) for k, i in zip(data["vocab_keys"], data["vocab_idx"])}
        return cls(
            weights=data["weights"],
            bias=float(data["bias"][0]),
            vocab=vocab,
            threshold=float(data["threshold"][0]),
            meta=json.loads(str(data["meta"][0])),
        )

    def explain(self, text: str, top_k: int = 6) -> list[tuple[str, float]]:
        """Features that moved this score, largest contribution first."""
        names = [""] * (len(self.vocab) + len(STRUCTURAL_FEATURES))
        for key, idx in self.vocab.items():
            names[idx] = key
        for offset, name in enumerate(STRUCTURAL_FEATURES):
            names[len(self.vocab) + offset] = name
        x = featurize([text], self.vocab)[0]
        contrib = x * self.weights
        order = np.argsort(-np.abs(contrib))[:top_k]
        return [(names[i], float(contrib[i])) for i in order if contrib[i] != 0.0]


def _sigmoid(z: np.ndarray) -> np.ndarray:
    # Branch on sign so exp never overflows on large-magnitude scores.
    out = np.empty_like(z, dtype=np.float64)
    pos, neg = z >= 0, z < 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[neg])
    out[neg] = ez / (1.0 + ez)
    return out


def train_logistic(
    X: np.ndarray,
    y: np.ndarray,
    *,
    l2: float = 1e-4,
    iterations: int = 400,
    learning_rate: float = 2.0,
    class_weight: bool = True,
) -> tuple[np.ndarray, float, list[float]]:
    """Full-batch gradient descent on regularised logistic loss.

    Deterministic by construction: zero initialisation, no sampling, no shuffling, a fixed
    iteration count. The problem is convex, so the optimum does not depend on the path.
    """
    n, d = X.shape
    w = np.zeros(d, dtype=np.float64)
    b = 0.0

    if class_weight:
        pos = float(max(y.sum(), 1.0))
        neg = float(max(n - y.sum(), 1.0))
        sample_w = np.where(y > 0.5, n / (2.0 * pos), n / (2.0 * neg))
    else:
        sample_w = np.ones(n, dtype=np.float64)
    sample_w /= sample_w.sum()

    Xd = X.astype(np.float64)
    history: list[float] = []
    for step in range(iterations):
        z = Xd @ w + b
        p = _sigmoid(z)
        eps = 1e-12
        loss = -float(np.sum(sample_w * (y * np.log(p + eps) + (1 - y) * np.log(1 - p + eps))))
        loss += 0.5 * l2 * float(w @ w)
        history.append(loss)

        resid = sample_w * (p - y)
        grad_w = Xd.T @ resid + l2 * w
        grad_b = float(resid.sum())

        # Decay keeps late steps from oscillating without needing a line search.
        lr = learning_rate / (1.0 + step / 100.0)
        w -= lr * grad_w
        b -= lr * grad_b

    return w, b, history


class SemanticClassifier:
    """Loads the trained artifact and scores text. Degrades to silence if absent."""

    def __init__(self, model_path: Path | None = None) -> None:
        self._model: TrainedModel | None = None
        path = model_path or default_model_path()
        if path and path.is_file():
            try:
                self._model = TrainedModel.load(path)
            except Exception:  # a corrupt artifact must not take the pipeline down
                self._model = None

    @property
    def available(self) -> bool:
        return self._model is not None

    @property
    def meta(self) -> dict:
        return (self._model.meta if self._model else {}) or {}

    def score(self, text: str) -> float | None:
        if not self._model or not (text or "").strip():
            return None
        return float(self._model.predict_proba([text])[0])

    def explain(self, text: str, top_k: int = 6) -> list[tuple[str, float]]:
        return self._model.explain(text, top_k) if self._model else []


def default_model_path() -> Path | None:
    """ontology/models/semantic_classifier.npz, found by walking up from this file."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "ontology" / "models" / "semantic_classifier.npz"
        if candidate.parent.is_dir() or candidate.is_file():
            return candidate
    return None
