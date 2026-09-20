"""Structured Virality Index output (advisory only).

Dimensions follow the sharing literature rather than intuition:

* ``arousal`` — Berger & Milkman (2012): high-activation emotion of *any* valence
  (awe, anger, anxiety, amusement) drives sharing; valence alone does not.
* ``social_currency``, ``practical_value``, ``story``, ``novelty``, ``triggers``,
  ``public_observability`` — Berger's STEPPS constructs.

``clarity`` and ``brand_prominence`` are reported as diagnostics but deliberately kept
out of the index. Clarity is comprehension hygiene, not a sharing driver, and brand
prominence is a *negative* predictor (Tellis, MacInnis, Tirunillai & Zhang, 2019).
Folding either into the total would require coefficients we have not fitted.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = "2.0"

DISCLAIMER = (
    "Virality Index is an advisory creative score, not a share prediction, "
    "and it does not replace compliance review. Weights are an unfitted uniform prior, "
    "so read the band and the per-dimension notes rather than the exact number."
)

DIMENSION_NAMES: tuple[str, ...] = (
    "arousal",
    "social_currency",
    "practical_value",
    "story",
    "novelty",
    "triggers",
    "public_observability",
)

# Uniform until fitted against real performance data. Equal weights are the honest
# default with no outcome data and are hard to beat with guessed ones
# (Dawes 1979, "The robust beauty of improper linear models").
WEIGHTS_SOURCE = "uniform_prior"
DIMENSION_WEIGHTS: dict[str, float] = {n: 1.0 / len(DIMENSION_NAMES) for n in DIMENSION_NAMES}

# The index is reported as a band, because the instrument cannot support 100 gradations.
# The dimensions are an LLM's judgement on an uncalibrated 0-100 scale with no
# inter-rater reliability behind it; summing them with unfitted weights does not create
# precision that was never in the inputs. 67 vs 64 is noise wearing a decimal point.
# Bands are what the evidence supports, and they are what the UI should show.
# When outcome data fits the weights (see ontology/examples/outcomes/), revisit this.
BANDS: tuple[tuple[int, str], ...] = ((34, "low"), (67, "moderate"), (101, "high"))


def virality_band(index: int) -> str:
    """Coarse bucket for an index. The reportable form of the score."""
    for ceiling, name in BANDS:
        if index < ceiling:
            return name
    return "high"


class ViralityDimensions(BaseModel):
    arousal: int = Field(ge=0, le=100, description="High-activation emotion, any valence")
    social_currency: int = Field(ge=0, le=100, description="Sharing signals identity / status")
    practical_value: int = Field(ge=0, le=100, description="Useful enough to be worth passing on")
    story: int = Field(ge=0, le=100, description="Narrative or dramatic arc")
    novelty: int = Field(ge=0, le=100, description="Surprise; violates expectation")
    triggers: int = Field(ge=0, le=100, description="Tied to a frequent environmental cue")
    public_observability: int = Field(ge=0, le=100, description="Visible or imitable behaviour")


class ViralityDiagnostics(BaseModel):
    """Reported, never summed into the index."""

    clarity: int = Field(default=50, ge=0, le=100, description="Comprehension gate, not a driver")
    brand_prominence: int = Field(
        default=0,
        ge=0,
        le=100,
        description="High branding correlates with reduced sharing (negative signal)",
    )


class ViralityReviewV2(BaseModel):
    schema_version: str = SCHEMA_VERSION
    virality_index: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Overall index; always recomputed from dimensions before storage",
    )
    weights_source: str = WEIGHTS_SOURCE
    band: str = Field(
        default="low",
        description="low | moderate | high — the reportable form; prefer this over the raw index",
    )
    scored_by: str = Field(
        default="unknown",
        description=(
            "gemini | heuristic — set by whichever path scored it. Surfaced so an offline "
            "heuristic estimate never reads as a model score; they are not comparable."
        ),
    )
    dimensions: ViralityDimensions
    diagnostics: ViralityDiagnostics = Field(default_factory=ViralityDiagnostics)
    closest_pattern_id: str | None = None
    closest_pattern_name: str | None = None
    pattern_match_strength: str = Field(default="none", description="strong|moderate|weak|none")
    suggestions: list[str] = Field(default_factory=list)
    summary: str = ""
    compliance_conflicts: list[str] = Field(default_factory=list)
    disclaimer: str = DISCLAIMER

    @field_validator("pattern_match_strength", mode="before")
    @classmethod
    def _norm_strength(cls, v: Any) -> str:
        s = str(v or "none").strip().lower()
        return s if s in ("strong", "moderate", "weak", "none") else "none"

    @field_validator("suggestions", "compliance_conflicts", mode="before")
    @classmethod
    def _clean_list(cls, v: Any) -> list[str]:
        """Models sometimes over-produce or return a bare string; never fail the run on it."""
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        items = [str(x).strip() for x in v if str(x).strip()]
        return items[:5]


def compute_virality_index(dim: ViralityDimensions) -> int:
    total = sum(w * float(getattr(dim, k)) for k, w in DIMENSION_WEIGHTS.items())
    return int(round(max(0.0, min(100.0, total))))


def diagnostic_flags(diag: ViralityDiagnostics) -> list[str]:
    """Human-readable caveats for signals that are reported but not scored."""
    flags: list[str] = []
    if diag.clarity < 40:
        flags.append(
            "Low clarity — unclear copy tends to suppress every other dimension, "
            "so treat the index as an upper bound."
        )
    if diag.brand_prominence >= 60:
        flags.append(
            "Heavy brand prominence — measured to reduce sharing (Tellis et al., 2019); "
            "consider holding the logo/name back until later in the creative."
        )
    return flags


def wrap_stored_virality(review: ViralityReviewV2) -> dict[str, Any]:
    """Serialize for storage, recomputing the index so it always matches the dimensions."""
    stored = review.model_dump()
    index = compute_virality_index(review.dimensions)
    stored["virality_index"] = index
    stored["band"] = virality_band(index)
    stored["diagnostic_flags"] = diagnostic_flags(review.diagnostics)
    return stored
