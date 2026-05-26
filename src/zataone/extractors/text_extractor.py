# zataone text extractor

"""
Production-grade TextExtractor for text assets.

Signal types emitted:
  keyword            — high-risk compliance keyword detected
  percentage_claim   — numeric percentage found (e.g. "99%")
  time_claim         — numeric time promise (e.g. "30 days")
  sentiment          — VADER compound score; positive/negative/neutral
  language           — detected language + confidence (langdetect)
  readability        — Flesch reading-ease score + grade level (pure Python)
  entity_monetary    — dollar amounts, "free", price language
  entity_contact     — email address, URL, phone number
  entity_medical     — medical/health claims, FDA references
  entity_legal       — warranty, liability, disclaimer language
  toxicity           — deceptive / manipulative advertising patterns

Sentiment and language signals degrade gracefully if their libraries are absent.
Pure extractor — no DB writes.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from zataone.extractors.base import BaseExtractor

logger = logging.getLogger(__name__)


# ── Keyword lists ─────────────────────────────────────────────────────────────

HIGH_RISK_KEYWORDS = [
    "guaranteed",
    "instant",
    "100%",
    "cure",
    "permanent",
    "no risk",
    "risk-free",
    "scientifically proven",
    "clinically proven",
    "results guaranteed",
    "money-back guarantee",
    "zero risk",
    "lose weight fast",
    "get rich quick",
    "unlimited income",
    "work from home",
    "financial freedom",
    "secret formula",
    "breakthrough",
    "revolutionary",
]


# ── Existing patterns ─────────────────────────────────────────────────────────

PERCENTAGE_PATTERN = re.compile(r"\d+%")
TIME_CLAIM_PATTERN = re.compile(r"\d+\s*(days?|hours?|minutes?|weeks?|months?)", re.IGNORECASE)


# ── P6: Entity patterns ───────────────────────────────────────────────────────

_MONETARY_RE = re.compile(
    r"""(?:
        \$\s*[\d,]+(?:\.\d{1,2})?                              # $1,234.56
        | [\d,]+(?:\.\d{1,2})?\s*(?:USD|EUR|GBP|CAD|AUD)\b    # 1234 USD
        | \bfree\b | \bFREE\b                                   # "free" claims
        | no[\s-]+charge | no[\s-]+cost | at[\s-]+no[\s-]+cost
    )""",
    re.VERBOSE | re.IGNORECASE,
)

_CONTACT_RE = re.compile(
    r"""(?:
        \b[\w.+\-]+@[\w\-]+\.[a-zA-Z]{2,}\b                   # email
        | (?:https?://|www\.)\S+                               # URL
        | \b(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}\b  # phone
    )""",
    re.VERBOSE,
)

_MEDICAL_RE = re.compile(
    r"""\b(?:
        treat(?:ment|s|ed|ing)?
        | cure[sd]?
        | heal(?:s|ing|ed|th)?
        | diagnos(?:e[sd]?|is|tic|ed)
        | prescri(?:be[sd]?|ption)
        | symptom[s]?
        | disease[s]?
        | disorder[s]?
        | FDA[\s\-]?approved
        | clinical[\s\-]?(?:trial|study|research)
        | medically[\s\-]proven
        | doctor[\s\-]recommended
        | physician[\s\-]tested
        | weight[\s\-]loss
        | anti[\s\-](?:aging|inflammatory|obesity)
        | detox(?:ify|ification)?
        | immune[\s\-](?:boost|support|system)
    )\b""",
    re.VERBOSE | re.IGNORECASE,
)

_LEGAL_RE = re.compile(
    r"""\b(?:
        warrant(?:y|ies|ed)?
        | liabilit(?:y|ies)
        | indemnif(?:y|ied|ication)
        | disclaimer[s]?
        | terms[\s\-]of[\s\-](?:service|use)
        | privacy[\s\-]policy
        | copyright
        | trademark
        | patent(?:ed|s|pending)?
        | class[\s\-]action
        | arbitration
        | jurisdiction
        | no[\s\-]refund
        | all[\s\-]sales[\s\-]final
        | non[\s\-]refundable
    )\b""",
    re.VERBOSE | re.IGNORECASE,
)

# Compliance-context deceptive/manipulative patterns
_TOXICITY_RE = re.compile(
    r"""\b(?:
        limited[\s\-]time[\s\-]offer
        | act[\s\-]now
        | don't[\s\-]miss[\s\-]out
        | exclusive[\s\-]offer
        | one[\s\-]time[\s\-]only
        | while[\s\-]supplies[\s\-]last
        | as[\s\-]seen[\s\-]on[\s\-](?:tv|television)
        | doctors?[\s\-]hate
        | they[\s\-]don't[\s\-]want[\s\-]you[\s\-]to[\s\-]know
        | secret[s]?[\s\-](?:they|doctors?|big[\s\-]\w+)
        | miracle[\s\-](?:cure|pill|solution|formula|ingredient)
        | click[\s\-]here[\s\-]now
        | lose[\s\-]+\d+[\s\-]+pounds
        | earn[\s\-]+\$[\d,]+[\s\-]+(?:per|a|in)[\s\-]+(?:day|week|month|hour)
    )\b""",
    re.VERBOSE | re.IGNORECASE,
)


# ── Optional library loader helpers ──────────────────────────────────────────

_vader_state: dict[str, Any] = {"checked": False, "available": False}
_langdetect_state: dict[str, Any] = {"checked": False, "available": False}


def _vader_available() -> bool:
    if _vader_state["checked"]:
        return _vader_state["available"]
    _vader_state["checked"] = True
    try:
        import nltk  # noqa: F401
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
        from nltk.sentiment.vader import SentimentIntensityAnalyzer  # noqa: F401
        _vader_state["available"] = True
    except Exception as exc:
        logger.warning(
            "VADER unavailable; sentiment signals disabled. "
            "Fix: pip install nltk && python -c \"import nltk; nltk.download('vader_lexicon')\". "
            "Reason: %s",
            exc,
        )
        _vader_state["available"] = False
    return _vader_state["available"]


def _langdetect_available() -> bool:
    if _langdetect_state["checked"]:
        return _langdetect_state["available"]
    _langdetect_state["checked"] = True
    try:
        import langdetect  # noqa: F401
        _langdetect_state["available"] = True
    except ImportError:
        logger.warning(
            "langdetect not installed; language signals disabled. "
            "Fix: pip install langdetect"
        )
        _langdetect_state["available"] = False
    return _langdetect_state["available"]


# ── Readability (pure Python) ─────────────────────────────────────────────────

_VOWEL_RE = re.compile(r"[aeiou]+", re.IGNORECASE)
_WORD_STRIP_RE = re.compile(r"[^a-zA-Z]")


def _count_syllables(word: str) -> int:
    word = _WORD_STRIP_RE.sub("", word).lower()
    if not word:
        return 1
    count = len(_VOWEL_RE.findall(word))
    if word.endswith("e") and count > 1:
        count -= 1
    return max(1, count)


def _flesch_reading_ease(text: str) -> tuple[float, str]:
    sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
    words = text.split()
    if not sentences or not words:
        return 0.0, "unknown"

    sentence_count = max(1, len(sentences))
    word_count = max(1, len(words))
    syllable_count = sum(_count_syllables(w) for w in words)

    score = 206.835 - 1.015 * (word_count / sentence_count) - 84.6 * (syllable_count / word_count)
    score = round(max(0.0, min(100.0, score)), 1)

    if score >= 70:
        grade = "easy"
    elif score >= 50:
        grade = "standard"
    elif score >= 30:
        grade = "difficult"
    else:
        grade = "very_difficult"

    return score, grade


# ── Signal dataclass ──────────────────────────────────────────────────────────


@dataclass
class Signal:
    """Signal emitted by TextExtractor. Conforms to pipeline Signal schema."""

    signal_id: str
    signal_type: str
    source_model: str
    confidence: float
    raw_data: dict
    bounding_box: None = None


# ── Extractor ─────────────────────────────────────────────────────────────────


class TextExtractor(BaseExtractor):
    """
    Text-based signal extractor for compliance-sensitive content.

    Emits keyword, pattern, NLP (sentiment, language, readability), entity, and
    toxicity signals. Sentiment and language degrade gracefully when their
    optional libraries (nltk, langdetect) are not installed.
    """

    extractor_id = "text_extractor"
    version = "2.0"

    # Minimum text length for meaningful NLP signals (chars)
    _NLP_MIN_LENGTH = 20

    def extract(self, asset: Any) -> list[Signal]:
        """
        Extract signals from a text asset.

        Args:
            asset: Object or dict with ``type`` (str) and ``content`` (str).

        Returns:
            List of Signal objects. Empty if asset.type != "text".
        """
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

        signals: list[Signal] = []
        content_lower = content.lower()

        # 1. High-risk keywords
        for keyword in HIGH_RISK_KEYWORDS:
            if keyword in content_lower:
                signals.append(self._make(
                    "keyword", 1.0,
                    {"type": "keyword", "text": keyword, "value": keyword},
                ))

        # 2. Percentage claims
        for match in PERCENTAGE_PATTERN.finditer(content):
            val = match.group(0)
            signals.append(self._make(
                "percentage_claim", 1.0,
                {"type": "percentage_claim", "text": val, "value": val,
                 "offset": match.start()},
            ))

        # 3. Time claims
        for match in TIME_CLAIM_PATTERN.finditer(content):
            val = match.group(0)
            signals.append(self._make(
                "time_claim", 1.0,
                {"type": "time_claim", "text": val, "value": val,
                 "offset": match.start()},
            ))

        # 4. Monetary entities
        for match in _MONETARY_RE.finditer(content):
            val = match.group(0)
            signals.append(self._make(
                "entity_monetary", 0.95,
                {"type": "entity_monetary", "text": val, "offset": match.start()},
            ))

        # 5. Contact entities (email / URL / phone)
        for match in _CONTACT_RE.finditer(content):
            val = match.group(0)
            signals.append(self._make(
                "entity_contact", 0.9,
                {"type": "entity_contact", "text": val, "offset": match.start()},
            ))

        # 6. Medical / health claims
        for match in _MEDICAL_RE.finditer(content):
            val = match.group(0)
            signals.append(self._make(
                "entity_medical", 0.85,
                {"type": "entity_medical", "text": val, "offset": match.start()},
            ))

        # 7. Legal language
        for match in _LEGAL_RE.finditer(content):
            val = match.group(0)
            signals.append(self._make(
                "entity_legal", 0.85,
                {"type": "entity_legal", "text": val, "offset": match.start()},
            ))

        # 8. Toxicity / deceptive patterns
        for match in _TOXICITY_RE.finditer(content):
            val = match.group(0)
            signals.append(self._make(
                "toxicity", 0.8,
                {"type": "toxicity", "text": val, "offset": match.start()},
            ))

        # NLP signals require a minimum text length
        if len(content) >= self._NLP_MIN_LENGTH:

            # 9. Sentiment (VADER)
            sentiment_sig = self._extract_sentiment(content)
            if sentiment_sig:
                signals.append(sentiment_sig)

            # 10. Language detection
            language_sig = self._extract_language(content)
            if language_sig:
                signals.append(language_sig)

            # 11. Readability
            signals.append(self._extract_readability(content))

        return signals

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _make(self, signal_type: str, confidence: float, raw_data: dict) -> Signal:
        return Signal(
            signal_id=str(uuid.uuid4()),
            signal_type=signal_type,
            source_model=self.extractor_id,
            confidence=confidence,
            raw_data=raw_data,
        )

    def _extract_sentiment(self, text: str) -> "Signal | None":
        if not _vader_available():
            return None
        try:
            from nltk.sentiment.vader import SentimentIntensityAnalyzer
            sia = SentimentIntensityAnalyzer()
            scores = sia.polarity_scores(text)
            compound = scores["compound"]
            if compound >= 0.05:
                label = "positive"
            elif compound <= -0.05:
                label = "negative"
            else:
                label = "neutral"
            return self._make(
                "sentiment",
                abs(compound) if compound != 0.0 else 0.5,
                {
                    "type": "sentiment",
                    "label": label,
                    "compound": round(compound, 4),
                    "positive": round(scores["pos"], 4),
                    "neutral": round(scores["neu"], 4),
                    "negative": round(scores["neg"], 4),
                },
            )
        except Exception as exc:
            logger.debug("Sentiment extraction failed: %s", exc)
            return None

    def _extract_language(self, text: str) -> "Signal | None":
        if not _langdetect_available():
            return None
        try:
            from langdetect import detect_langs
            results = detect_langs(text)
            if not results:
                return None
            top = results[0]
            return self._make(
                "language",
                round(float(top.prob), 4),
                {
                    "type": "language",
                    "language": top.lang,
                    "confidence": round(float(top.prob), 4),
                    "all_detected": [
                        {"lang": r.lang, "prob": round(float(r.prob), 4)}
                        for r in results
                    ],
                },
            )
        except Exception as exc:
            logger.debug("Language detection failed: %s", exc)
            return None

    def _extract_readability(self, text: str) -> Signal:
        score, grade = _flesch_reading_ease(text)
        words = text.split()
        sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
        return self._make(
            "readability",
            1.0,
            {
                "type": "readability",
                "flesch_reading_ease": score,
                "grade": grade,
                "word_count": len(words),
                "sentence_count": len(sentences),
            },
        )
