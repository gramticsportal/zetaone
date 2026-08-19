# zataone semantic text extractor (first real ML sensor for the text path)

"""
SemanticTextExtractor — sentence-embedding similarity against regulation exemplars.

Runs as a parallel sensor alongside TextExtractor. It never decides violations:
it emits ``text_embedding_similarity`` signals (regulation + score) that the
policy engine fuses into rules via EMBEDDING_RULE_MAP, the same channel the
SigLIP image embedding extractor uses. This catches paraphrases the keyword
lists miss ("melts fat away in no time" ~ medical/weight-loss claims) while
keeping the deterministic DSL as the only judge.

Model: sentence-transformers/all-MiniLM-L6-v2 via transformers (mean pooling).
Degrades gracefully — if torch/transformers are absent or the model fails to
load, the extractor logs once and emits no signals.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path
from typing import Any

from zataone.extractors.base import BaseExtractor
from zataone.extractors.text_extractor import Signal

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Harvest category_ids → regulation names used by EMBEDDING_RULE_MAP *values*.
_CATEGORY_TO_REGULATION = {
    "misleading": "misleading_claims",
    "health": "medical_health_claims",
    "financial": "financial_products_and_guarantees",
    "gambling": "gambling",
    "drugs": "tobacco_nicotine",
    "privacy": "fraud_scams_deceptive",
}

# Toy fallbacks for categories with no harvested copy (weapons, crypto). Used only
# when a regulation has nothing in eval_harvested.yaml.
_FALLBACK_EXEMPLARS: dict[str, list[str]] = {
    "misleading_claims": [
        "guaranteed results with no effort required",
        "this product works instantly for everyone",
        "scientifically proven breakthrough with amazing results",
    ],
    "medical_health_claims": [
        "cures diseases and heals your body permanently",
        "lose weight fast without diet or exercise",
        "doctor recommended treatment that eliminates symptoms",
    ],
    "fraud_scams_deceptive": [
        "act now limited time offer they don't want you to know",
        "get rich quick with this secret money making system",
        "earn thousands per week working from home with no experience",
    ],
    "weapons_ammunition_explosives": [
        "buy firearms guns ammunition and explosives online",
    ],
    "tobacco_nicotine": [
        "cigarettes vaping nicotine products for sale",
    ],
    "gambling": [
        "online casino betting win real money jackpot",
    ],
    "financial_products_and_guarantees": [
        "guaranteed investment returns with zero risk to your money",
        "instant loan approval no credit check required",
    ],
    "cryptocurrency_services": [
        "buy bitcoin cryptocurrency trading guaranteed profits",
    ],
}

# Backward-compatible name: tests and callers that pass exemplars explicitly never
# hit this. Default construction loads harvested copy via load_harvest_exemplars().
REGULATION_EXEMPLARS = _FALLBACK_EXEMPLARS

_MAX_EXEMPLARS_PER_REG = 80


def _harvest_path() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "ontology" / "examples" / "eval_harvested.yaml"
        if candidate.is_file():
            return candidate
    return None


def load_harvest_exemplars(
    *,
    harvest_path: Path | None = None,
    exclude_ids: set[str] | None = None,
    max_per_regulation: int = _MAX_EXEMPLARS_PER_REG,
) -> dict[str, list[str]]:
    """Verbatim enforcement copy, grouped by regulation, longest-first.

    Falls back to the hand-written toys only for regulations the harvest does not
    cover (weapons, crypto). Cap keeps startup encoding cheap; 80 phrases per
    bucket is well past the point of diminishing returns for MiniLM.
    """
    from collections import defaultdict

    import yaml

    out: dict[str, list[str]] = defaultdict(list)
    path = harvest_path or _harvest_path()
    skip = exclude_ids or set()
    if path and path.is_file():
        rows = (yaml.safe_load(path.read_text()) or {}).get("examples") or []
        for row in rows:
            if row.get("id") in skip:
                continue
            text = (row.get("content") or "").strip()
            if len(text) < 15:
                continue
            for cat in row.get("category_ids") or []:
                reg = _CATEGORY_TO_REGULATION.get(cat)
                if reg:
                    out[reg].append(text)
        for reg, texts in list(out.items()):
            # Longest first: short fragments survived the quality audit less often,
            # and MiniLM is more stable on a full claim than on a slogan.
            uniq = sorted(set(texts), key=len, reverse=True)
            out[reg] = uniq[:max_per_regulation]
    for reg, phrases in _FALLBACK_EXEMPLARS.items():
        if not out.get(reg):
            out[reg] = list(phrases)
    return dict(out)


_SENTENCE_SPLIT_RE = re.compile(r"[.!?\n]+")

# Lazy singleton model state; mirrors the optional-library pattern in text_extractor.
_model_state: dict[str, Any] = {"checked": False, "encoder": None}


def _load_encoder(model_name: str) -> Any | None:
    """Load tokenizer+model once; return None (and warn once) if unavailable."""
    if _model_state["checked"]:
        return _model_state["encoder"]
    _model_state["checked"] = True
    try:
        import torch
        from transformers import AutoModel, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
        model.eval()

        def encode(texts: list[str]) -> Any:
            with torch.no_grad():
                batch = tokenizer(
                    texts, padding=True, truncation=True, max_length=256, return_tensors="pt"
                )
                output = model(**batch)
                # Mean pooling over valid tokens
                mask = batch["attention_mask"].unsqueeze(-1).float()
                summed = (output.last_hidden_state * mask).sum(dim=1)
                counts = mask.sum(dim=1).clamp(min=1e-9)
                embeddings = summed / counts
                return torch.nn.functional.normalize(embeddings, p=2, dim=1)

        _model_state["encoder"] = encode
    except Exception as exc:
        logger.warning(
            "Semantic text model unavailable; semantic signals disabled. "
            "Fix: pip install torch transformers (model: %s). Reason: %s",
            model_name,
            exc,
        )
        _model_state["encoder"] = None
    return _model_state["encoder"]


class SemanticTextExtractor(BaseExtractor):
    """
    ML sensor: embeds ad text and scores similarity to regulation exemplars.

    Emits Signal(signal_type="semantic_similarity") with
    raw_data = {type: "text_embedding_similarity", regulation, score, ...}.
    Pure extractor — no DB writes, no verdicts.
    """

    extractor_id = "semantic_text_extractor"
    version = "1.0"

    _MIN_TEXT_LENGTH = 15  # chars; below this, embeddings are noise

    def __init__(
        self,
        similarity_threshold: float = 0.5,
        model_name: str = DEFAULT_MODEL_NAME,
        exemplars: dict[str, list[str]] | None = None,
        encoder: Any | None = None,
    ) -> None:
        self._similarity_threshold = similarity_threshold
        self._model_name = model_name
        self._exemplars = exemplars if exemplars is not None else load_harvest_exemplars()
        self._encoder = encoder  # injectable for tests
        self._exemplar_cache: tuple[list[str], Any] | None = None

    # ── Extraction ────────────────────────────────────────────────────────────

    def extract(self, asset: Any) -> list[Signal]:
        asset_type = (
            asset.get("type") if isinstance(asset, dict) else getattr(asset, "type", None)
        )
        if asset_type != "text":
            return []

        content = (
            asset.get("content", "") if isinstance(asset, dict) else getattr(asset, "content", "")
        ) or ""
        if not isinstance(content, str):
            content = str(content)
        if len(content.strip()) < self._MIN_TEXT_LENGTH:
            return []

        encoder = self._encoder or _load_encoder(self._model_name)
        if encoder is None:
            return []

        try:
            return self._score(content, encoder)
        except Exception as exc:
            logger.exception("SemanticTextExtractor failed: %s", exc)
            return []

    def _score(self, content: str, encoder: Any) -> list[Signal]:
        # Score whole text plus individual sentences so one risky sentence
        # inside long copy still surfaces.
        candidates = [content.strip()]
        for sent in _SENTENCE_SPLIT_RE.split(content):
            sent = sent.strip()
            if len(sent) >= self._MIN_TEXT_LENGTH and sent != candidates[0]:
                candidates.append(sent)

        reg_names, reg_matrix = self._encoded_exemplars(encoder)
        text_matrix = encoder(candidates)

        # Cosine similarity (embeddings are L2-normalized): candidates x exemplars
        sims = text_matrix @ reg_matrix.T

        best: dict[str, tuple[float, str]] = {}
        for ci, candidate in enumerate(candidates):
            for ei, reg in enumerate(reg_names):
                score = float(sims[ci][ei])
                if score <= self._similarity_threshold:
                    continue
                prev = best.get(reg)
                if prev is None or score > prev[0]:
                    best[reg] = (score, candidate)

        signals: list[Signal] = []
        for reg, (score, candidate) in best.items():
            signals.append(
                Signal(
                    signal_id=str(uuid.uuid4()),
                    signal_type="semantic_similarity",
                    source_model=self.extractor_id,
                    confidence=round(score, 4),
                    raw_data={
                        "type": "text_embedding_similarity",
                        "regulation": reg,
                        "score": round(score, 4),
                        "matched_text": candidate[:200],
                        "model": self._model_name,
                    },
                )
            )
        logger.info("SemanticTextExtractor produced %d signals", len(signals))
        return signals

    def _encoded_exemplars(self, encoder: Any) -> tuple[list[str], Any]:
        """Encode exemplars once per extractor instance; regulation per row."""
        if self._exemplar_cache is not None:
            return self._exemplar_cache
        names: list[str] = []
        texts: list[str] = []
        for reg, phrases in self._exemplars.items():
            for phrase in phrases:
                names.append(reg)
                texts.append(phrase)
        self._exemplar_cache = (names, encoder(texts))
        return self._exemplar_cache
