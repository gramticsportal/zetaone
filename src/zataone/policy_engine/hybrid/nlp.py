# zataone hybrid NLP scorer — sentence embeddings + BoW cosine fallback

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Any

import numpy as np

from zataone.policy_engine.hybrid.flags import hybrid_nlp_backend, hybrid_nlp_model_id, hybrid_nlp_threshold
from zataone.policy_engine.hybrid.pack_loader import PatternPack

logger = logging.getLogger(__name__)

# Named backends → HuggingFace model ids (mean-pool + L2, transformers).
NLP_MODEL_REGISTRY: dict[str, str] = {
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",
    "minilm_l12": "sentence-transformers/all-MiniLM-L12-v2",
    "bge_small": "BAAI/bge-small-en-v1.5",
    "e5_small": "intfloat/e5-small-v2",
}

# e5 expects asymmetric prefixes for best quality.
_E5_QUERY_PREFIX = "query: "
_E5_PASSAGE_PREFIX = "passage: "


def _stem(tok: str) -> str:
    """Light suffix strip so cure/cures and eliminate/eliminates overlap in BoW."""
    if len(tok) <= 3:
        return tok
    if tok.endswith("ing") and len(tok) > 5:
        return tok[:-3]
    if tok.endswith("ed") and len(tok) > 4:
        return tok[:-2]
    if tok.endswith("s") and not tok.endswith("ss") and len(tok) > 3:
        return tok[:-1]
    return tok


def _tokenize(text: str) -> list[str]:
    return [_stem(t) for t in re.findall(r"[a-z0-9%]{2,}", (text or "").lower())]


def _bow_vector(text: str, vocab: dict[str, int] | None = None) -> tuple[np.ndarray, dict[str, int]]:
    tokens = _tokenize(text)
    grams: list[str] = list(tokens)
    compact = re.sub(r"\s+", "", (text or "").lower())
    for i in range(max(0, len(compact) - 2)):
        grams.append(compact[i : i + 3])
    counts = Counter(grams)
    if vocab is None:
        vocab = {t: i for i, t in enumerate(sorted(counts.keys()))}
    vec = np.zeros(len(vocab), dtype=np.float32)
    for t, c in counts.items():
        if t in vocab:
            vec[vocab[t]] = float(c)
    n = float(np.linalg.norm(vec))
    if n > 0:
        vec /= n
    return vec, vocab


_BOW_STOP = frozenset(
    "a an the and or to of in on for with this that from by is are was were be "
    "claims claim must not without including such".split()
)


def _word_jaccard(a: str, b: str) -> float:
    ta, tb = set(_tokenize(a)), set(_tokenize(b))
    if not ta or not tb:
        return 0.0
    return float(len(ta & tb) / len(ta | tb))


def _proto_coverage(doc: str, proto: str) -> float:
    """Fraction of informative prototype tokens present in the document."""
    ta = {t for t in _tokenize(doc) if t not in _BOW_STOP and len(t) > 3}
    tb = {t for t in _tokenize(proto) if t not in _BOW_STOP and len(t) > 3}
    if not tb:
        return 0.0
    return float(len(ta & tb) / len(tb))


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    if a.shape != b.shape:
        m = max(a.size, b.size)
        aa = np.zeros(m, dtype=np.float32)
        bb = np.zeros(m, dtype=np.float32)
        aa[: a.size] = a
        bb[: b.size] = b
        a, b = aa, bb
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def resolve_embedding_model_id(backend: str) -> str | None:
    """Return HF model id for a neural backend name, else None (bow/auto handled elsewhere)."""
    override = hybrid_nlp_model_id()
    if override:
        return override
    if backend in NLP_MODEL_REGISTRY:
        return NLP_MODEL_REGISTRY[backend]
    return None


class HybridNLPScorer:
    """
    Semantic similarity of document text vs pack embedding_prototypes / detection summaries.

    Backends:
      - bow
      - minilm | minilm_l12 | bge_small | e5_small  (transformers mean-pool)
      - auto: try minilm, fall back to bow
      - Or set ZATAONE_HYBRID_NLP_MODEL to any HF sentence encoder id
    """

    def __init__(self) -> None:
        self._backend = hybrid_nlp_backend()
        self._threshold = hybrid_nlp_threshold()
        self._model = None
        self._tokenizer = None
        self._model_id: str | None = None
        self._active = "bow"
        self._use_e5_prefixes = False
        self._doc_cache_key: str | None = None
        self._doc_cache_emb: np.ndarray | None = None
        self._init_backend()

    def _init_backend(self) -> None:
        want = self._backend
        neural_names = set(NLP_MODEL_REGISTRY) | {"auto"}
        if want in neural_names or want == "minilm" or hybrid_nlp_model_id():
            target = "minilm" if want == "auto" else want
            model_id = resolve_embedding_model_id(target) or NLP_MODEL_REGISTRY["minilm"]
            if self._try_load_transformer(model_id):
                self._active = target if target != "auto" else "minilm"
                self._model_id = model_id
                self._use_e5_prefixes = "e5-" in model_id.lower() or self._active == "e5_small"
                logger.info("hybrid NLP: using %s (%s)", self._active, model_id)
                return
            if want not in ("auto", "bow"):
                logger.warning(
                    "hybrid NLP: %s unavailable; using BoW", want
                )
        self._active = "bow"
        self._model_id = None
        logger.info("hybrid NLP: using bag-of-words cosine fallback")

    def _try_load_transformer(self, model_id: str) -> bool:
        try:
            from transformers import AutoModel, AutoTokenizer
            import torch

            self._tokenizer = AutoTokenizer.from_pretrained(model_id)
            self._model = AutoModel.from_pretrained(model_id)
            self._model.eval()
            self._torch = torch
            self._encode_transformer(["warmup"])
            return True
        except Exception as e:
            logger.info("hybrid NLP transformer unavailable (%s): %s", model_id, e)
            self._model = None
            self._tokenizer = None
            return False

    def _prefix_texts(self, texts: list[str], *, role: str) -> list[str]:
        if not self._use_e5_prefixes:
            return texts
        pfx = _E5_QUERY_PREFIX if role == "query" else _E5_PASSAGE_PREFIX
        return [pfx + (t or "") for t in texts]

    def _encode_transformer(self, texts: list[str]) -> np.ndarray:
        assert self._model is not None and self._tokenizer is not None
        torch = self._torch
        enc = self._tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=256,
            return_tensors="pt",
        )
        with torch.no_grad():
            out = self._model(**enc)
            mask = enc["attention_mask"].unsqueeze(-1).expand(out.last_hidden_state.size()).float()
            summed = torch.sum(out.last_hidden_state * mask, dim=1)
            counts = torch.clamp(mask.sum(dim=1), min=1e-9)
            emb = summed / counts
            emb = torch.nn.functional.normalize(emb, p=2, dim=1)
        return emb.cpu().numpy().astype(np.float32)

    def encode(self, texts: list[str], *, role: str = "passage") -> np.ndarray:
        texts = [t if t and t.strip() else " " for t in texts]
        if self._active != "bow" and self._model is not None:
            return self._encode_transformer(self._prefix_texts(texts, role=role))
        # BoW: union vocab across the whole batch, then vectorize
        all_tokens: set[str] = set()
        tokenized: list[Counter] = []
        for t in texts:
            tokens = _tokenize(t)
            grams: list[str] = list(tokens)
            compact = re.sub(r"\s+", "", (t or "").lower())
            for i in range(max(0, len(compact) - 2)):
                grams.append(compact[i : i + 3])
            counts = Counter(grams)
            tokenized.append(counts)
            all_tokens.update(counts.keys())
        vocab = {tok: i for i, tok in enumerate(sorted(all_tokens))}
        rows = []
        for counts in tokenized:
            vec = np.zeros(len(vocab), dtype=np.float32)
            for tok, c in counts.items():
                vec[vocab[tok]] = float(c)
            n = float(np.linalg.norm(vec))
            if n > 0:
                vec /= n
            rows.append(vec)
        return np.stack(rows, axis=0) if rows else np.zeros((0, 0), dtype=np.float32)

    def _doc_embedding(self, document_text: str) -> np.ndarray:
        key = document_text[:4000]
        if self._doc_cache_key == key and self._doc_cache_emb is not None:
            return self._doc_cache_emb
        emb = self.encode([key], role="query")[0]
        self._doc_cache_key = key
        self._doc_cache_emb = emb
        return emb

    def score_pack(self, document_text: str, pack: PatternPack) -> dict[str, Any] | None:
        """Return NLP hit dict if similarity >= threshold, else None."""
        prototypes = [
            p for p in (pack.embedding_prototypes or pack.detection_summaries or []) if p and p.strip()
        ]
        if not prototypes or not (document_text or "").strip():
            return None
        prototypes = prototypes[:5]
        try:
            if self._active == "bow":
                # BoW needs shared vocab across doc+protos
                embs = self.encode([document_text[:4000], *prototypes])
                doc_emb = embs[0]
                proto_embs = embs[1:]
            else:
                doc_emb = self._doc_embedding(document_text)
                proto_embs = self.encode(prototypes, role="passage")
        except Exception:
            logger.exception("hybrid NLP encode failed")
            return None
        if proto_embs.shape[0] < 1:
            return None
        best_score = -1.0
        best_proto = ""
        for i, proto in enumerate(prototypes):
            score = float(np.dot(doc_emb, proto_embs[i]))
            if not math.isfinite(score):
                score = _cosine(doc_emb, proto_embs[i])
            if self._active == "bow":
                score = max(
                    score,
                    _word_jaccard(document_text, proto),
                    _proto_coverage(document_text, proto),
                )
            if score > best_score:
                best_score = score
                best_proto = proto
        thr = self._threshold
        if self._active == "bow":
            thr = min(thr, 0.22)
        if best_score < thr:
            return None
        return {
            "matcher": "nlp_embedding",
            "backend": self._active,
            "model_id": self._model_id,
            "score": best_score,
            "confidence": min(0.95, max(0.55, best_score)),
            "prototype": best_proto[:300],
            "threshold": thr,
        }

    @property
    def backend(self) -> str:
        return self._active

    @property
    def model_id(self) -> str | None:
        return self._model_id
