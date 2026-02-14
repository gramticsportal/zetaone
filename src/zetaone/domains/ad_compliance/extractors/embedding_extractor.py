"""
SigLIP embedding similarity extractor.

Compares image embeddings to regulation text embeddings for supporting evidence.
Inherits from zetaone.extractors.base.BaseExtractor.
"""

from typing import List, Optional, Tuple, Any
import sys
import os
import uuid
from io import BytesIO
from datetime import datetime
import numpy as np

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

_zetaone_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_src_root = os.path.dirname(_zetaone_dir)
if os.path.exists(os.path.join(_zetaone_dir, "extractors", "base.py")):
    if _src_root not in sys.path:
        sys.path.insert(0, _src_root)

try:
    from zetaone.extractors.base import BaseExtractor
except ImportError:
    from abc import ABC, abstractmethod
    class BaseExtractor(ABC):
        extractor_id: str = ""
        version: str = ""
        @abstractmethod
        def extract(self, asset): pass
from schemas.models import Signal, SignalType

try:
    from transformers import AutoProcessor, AutoModel
    import torch
    from PIL import Image
    SIGLIP_AVAILABLE = True
except ImportError:
    SIGLIP_AVAILABLE = False

_model: Optional[AutoModel] = None
_processor: Optional[AutoProcessor] = None
_device: Optional[str] = None
_text_embedding_cache: dict = {}


def _extract_embedding_tensor(output) -> "torch.Tensor":
    if hasattr(output, "pooler_output") and output.pooler_output is not None:
        return output.pooler_output
    elif hasattr(output, "last_hidden_state") and output.last_hidden_state is not None:
        return output.last_hidden_state[:, 0, :]
    return output[0] if hasattr(output, "__getitem__") else output


def _get_model():
    global _model, _processor, _device
    if _model is None:
        if not SIGLIP_AVAILABLE:
            raise ImportError(
                "transformers and torch are required for SigLIP. "
                "Install with: pip install transformers torch pillow"
            )
        model_name = "google/siglip-base-patch16-224"
        _processor = AutoProcessor.from_pretrained(model_name)
        _model = AutoModel.from_pretrained(model_name)
        _device = "cuda" if torch.cuda.is_available() else "cpu"
        _model = _model.to(_device)
        _model.eval()
    return _model, _processor, _device


def encode_regulation_texts(regulation_texts: List[Tuple[str, str]]) -> List[np.ndarray]:
    """Encode regulation text strings into normalized embeddings. Uses cache."""
    global _text_embedding_cache
    if not SIGLIP_AVAILABLE:
        raise ImportError("transformers and torch are required for text encoding.")
    model, processor, device = _get_model()
    embeddings = []
    texts_to_encode = []
    text_indices = []
    for i, (name, text) in enumerate(regulation_texts):
        if text in _text_embedding_cache:
            embeddings.append((i, _text_embedding_cache[text]))
        else:
            texts_to_encode.append(text)
            text_indices.append(i)
    if texts_to_encode:
        inputs = processor(text=texts_to_encode, return_tensors="pt", padding="max_length", truncation=True)
        inputs = {k: v.to(device) for k, v in inputs.items()}
        with torch.no_grad():
            out = model.get_text_features(**inputs)
            t = _extract_embedding_tensor(out)
            text_embeds = t.detach().cpu().numpy()
        for idx, (text, embedding) in enumerate(zip(texts_to_encode, text_embeds)):
            norm = np.linalg.norm(embedding)
            if norm > 0:
                embedding = embedding / norm
            embedding = embedding.astype(np.float32)
            _text_embedding_cache[text] = embedding
            embeddings.append((text_indices[idx], embedding))
    embeddings.sort(key=lambda x: x[0])
    return [emb for _, emb in embeddings]


class EmbeddingExtractor(BaseExtractor):
    """SigLIP-based embedding similarity extractor."""

    extractor_id = "ad_compliance_embedding"
    version = "1.0.0"

    def __init__(
        self,
        regulation_texts: List[Tuple[str, str]] = None,
        similarity_threshold: float = 0.6,
    ):
        self.model_name = "siglip"
        self._regulation_texts = regulation_texts or [
            ("misleading_claims", "misleading or exaggerated advertising claims"),
            ("medical_health_claims", "unsubstantiated or guaranteed medical or health claims"),
            ("fraud_scams_deceptive", "fraud scams and deceptive practices financial urgency impersonation"),
            ("weapons_ammunition_explosives", "weapons ammunition explosives restricted goods"),
            ("tobacco_nicotine", "tobacco nicotine products vaping restricted"),
            ("gambling", "gambling betting casino restricted"),
            ("financial_products_and_guarantees", "financial products guarantees loans investment insurance"),
            ("cryptocurrency_services", "cryptocurrency crypto bitcoin trading exchange financial"),
        ]
        self._similarity_threshold = similarity_threshold
        self._model = None
        self._processor = None
        self._device = None

    def _load_model(self):
        if self._model is None:
            self._model, self._processor, self._device = _get_model()

    def extract_embedding(self, image_data: bytes) -> np.ndarray:
        """Extract normalized image embedding (public for testing)."""
        return self._extract_embedding_impl(image_data)

    def _extract_embedding_impl(self, image_data: bytes) -> np.ndarray:
        self._load_model()
        image = Image.open(BytesIO(image_data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        inputs = self._processor(images=image, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}
        with torch.no_grad():
            features = self._model.get_image_features(**inputs)
            t = _extract_embedding_tensor(features)
            if t.dim() > 1:
                t = t[0]
            embedding = t.detach().cpu().numpy()
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding.astype(np.float32)

    def extract(self, asset: Any) -> List[Signal]:
        """Extract similarity signals (only when above threshold)."""
        image_data = getattr(asset, "image_data", None)
        if image_data is None or not self._regulation_texts or not SIGLIP_AVAILABLE:
            return []
        self._load_model()
        image_emb = self._extract_embedding_impl(image_data)
        text_embs = encode_regulation_texts(self._regulation_texts)
        names = [n for n, _ in self._regulation_texts]
        signals = []
        for name, text_emb in zip(names, text_embs):
            dot_result = np.dot(image_emb, text_emb)
            cos_sim = float(np.asarray(dot_result).ravel()[0])
            score = max(0.0, min(1.0, (cos_sim + 1.0) / 2.0))
            if score <= self._similarity_threshold:
                continue
            raw = {
                "type": "image_embedding_similarity",
                "regulation": name,
                "score": score,
                "model": self.model_name,
            }
            sig = Signal(
                signal_id=str(uuid.uuid4()),
                signal_type=SignalType.SCENE,
                source_model=self.model_name,
                confidence=score,
                raw_data=raw,
                bounding_box=None,
                detected_at=datetime.now(),
            )
            signals.append(sig)
        return signals
