"""
Creative performance outcomes — the data that turns the Virality Index from an
opinion into a fitted instrument.

The Index ships ``weights_source="uniform_prior"``: seven dimensions, equal weights,
no outcome data behind them. Equal weighting is the honest default with nothing
fitted (Dawes 1979) but it is not *substantiated*, and an objective performance
claim needs a reasonable basis before it is made — the same standard
``ftc.misleading.reasonable_basis`` holds our customers to. This module defines the
minimum we must collect to earn that basis.

Three design decisions, because they are what make the data usable rather than
merely plentiful:

1. **The comparison set is the unit of learning, not the creative.** Absolute
   virality is dominated by spend, seeding, timing and the platform algorithm —
   none of which live in the copy, and which swamp creative effects entirely
   (Salganik, Dodds & Watts 2006, where identical songs diverged wildly across
   parallel worlds). Ranking variants that ran *under the same conditions* removes
   most of that confounding in one step. One creative with no sibling teaches us
   almost nothing; four variants from one ad set teach us a great deal.

2. **Coarse outcomes are first-class.** A design partner will say "the second one
   did best" long before they hand over CPM. A three-way ordinal answer is enough
   to fit a ranker, so nothing here requires numbers we will never be given.

3. **Provenance is recorded, never inferred.** Customer-reported, platform API and
   ad-library observations carry very different reliability, and scraped "top ads"
   galleries are survivorship-biased by construction — they contain no losers, so
   they cannot teach the contrast we need. ``source`` keeps them separable at fit
   time rather than silently pooled.

What this deliberately does **not** model: absolute share counts, a virality
prediction, or any cross-campaign comparison. Those are the parts that do not
survive contact with the confounders.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"

PLATFORMS: tuple[str, ...] = (
    "meta",
    "tiktok",
    "youtube",
    "x",
    "linkedin",
    "reddit",
    "pinterest",
    "snap",
    "other",
)

FORMATS: tuple[str, ...] = ("static_image", "video", "carousel", "text", "audio", "other")

# Ordinal, and ordered. Index position is the rank target when no metric is given.
RELATIVE_GRADES: tuple[str, ...] = ("underperformed", "on_par", "outperformed")

# Reliability descends down this list; `ad_library` is survivorship-biased and must
# never be pooled with reported outcomes without a source term in the model.
OUTCOME_SOURCES: tuple[str, ...] = (
    "platform_api",
    "customer_reported",
    "manual_annotation",
    "ad_library",
)

# Below this, a "comparison" is really two different campaigns wearing one label.
MAX_SPEND_RATIO = 3.0
MIN_IMPRESSIONS_FOR_METRIC = 1000


def _norm(value: Any, allowed: tuple[str, ...], default: str) -> str:
    s = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    return s if s in allowed else default


class ExposureContext(BaseModel):
    """
    Everything that moves performance and is *not* the creative.

    Recorded so it can be held constant (within a comparison set) or controlled for
    (across them). A model fitted without these learns which advertiser had budget.
    """

    platform: str = "other"
    placement: str = Field(default="", description="feed | stories | reels | search | in_stream …")
    format: str = "other"
    audience_key: str = Field(
        default="",
        description=(
            "Opaque, stable hash of the targeting spec. Never raw audience data — it only "
            "has to be equal for two variants that shared an audience."
        ),
    )
    spend_usd: float | None = Field(default=None, ge=0)
    impressions: int | None = Field(default=None, ge=0)
    reach: int | None = Field(default=None, ge=0)
    flight_start: date | None = None
    flight_end: date | None = None

    @field_validator("platform", mode="before")
    @classmethod
    def _p(cls, v: Any) -> str:
        return _norm(v, PLATFORMS, "other")

    @field_validator("format", mode="before")
    @classmethod
    def _f(cls, v: Any) -> str:
        return _norm(v, FORMATS, "other")


class CreativeOutcome(BaseModel):
    """
    How one creative variant actually performed.

    Either ``relative_grade`` or at least one rate metric must be present — a record
    with neither carries no signal and is rejected rather than stored as a silent
    null that pollutes a fit later.
    """

    schema_version: str = SCHEMA_VERSION
    outcome_id: str
    variant_label: str = Field(default="", description="Human label, e.g. 'hook A · no logo'")

    # Links back into the ZataOne run that scored this creative, so dimensions and
    # outcomes can be joined without re-scoring.
    asset_id: str | None = None
    virality_schema_version: str | None = None

    exposure: ExposureContext = Field(default_factory=ExposureContext)

    # Precise metrics — rates, never raw counts, because counts encode spend.
    ctr: float | None = Field(default=None, ge=0, le=1)
    engagement_rate: float | None = Field(default=None, ge=0, le=1)
    share_rate: float | None = Field(default=None, ge=0, le=1)
    video_completion_rate: float | None = Field(default=None, ge=0, le=1)

    # Coarse fallback, and the only thing many partners will give us.
    relative_grade: str | None = Field(
        default=None, description=" | ".join(RELATIVE_GRADES)
    )

    source: str = "customer_reported"
    observed_at: date | None = None
    notes: str = ""

    @field_validator("relative_grade", mode="before")
    @classmethod
    def _g(cls, v: Any) -> str | None:
        if v is None or str(v).strip() == "":
            return None
        return _norm(v, RELATIVE_GRADES, "on_par")

    @field_validator("source", mode="before")
    @classmethod
    def _s(cls, v: Any) -> str:
        return _norm(v, OUTCOME_SOURCES, "customer_reported")

    @model_validator(mode="after")
    def _needs_a_signal(self) -> CreativeOutcome:
        if self.relative_grade is None and self.primary_metric() is None:
            raise ValueError(
                f"outcome {self.outcome_id!r} carries no signal: "
                "give a relative_grade or at least one rate metric"
            )
        return self

    def primary_metric(self) -> float | None:
        """
        The rate we rank on, in preference order.

        Engagement first because it is the closest observable to sharing intent;
        CTR last because it is the most sensitive to placement and offer rather
        than to the creative itself.
        """
        for m in (self.share_rate, self.engagement_rate, self.video_completion_rate, self.ctr):
            if m is not None:
                return m
        return None

    def metric_is_trustworthy(self) -> bool:
        """A rate over a few hundred impressions is noise wearing a decimal point."""
        imp = self.exposure.impressions
        return self.primary_metric() is not None and (
            imp is None or imp >= MIN_IMPRESSIONS_FOR_METRIC
        )

    def rank_value(self) -> float | None:
        """Sortable performance value: the rate if we have one, else the ordinal grade."""
        if self.metric_is_trustworthy():
            return self.primary_metric()
        if self.relative_grade is not None:
            return float(RELATIVE_GRADES.index(self.relative_grade))
        return None


class ComparisonSet(BaseModel):
    """
    Variants that ran under the same conditions — the actual training unit.

    ``campaign_id`` is also the **split grouping key**: every variant of a campaign
    lands in the same train/dev/test split, exactly as every row derived from one
    enforcement precedent shares a split in the compliance eval. Splitting variants
    of one campaign across train and test leaks the answer.
    """

    schema_version: str = SCHEMA_VERSION
    campaign_id: str
    advertiser_id: str = ""
    outcomes: list[CreativeOutcome] = Field(default_factory=list)
    notes: str = ""

    @property
    def is_rankable(self) -> bool:
        """Two variants with distinguishable performance is the minimum useful set."""
        vals = [o.rank_value() for o in self.outcomes]
        present = [v for v in vals if v is not None]
        return len(present) >= 2 and len(set(present)) >= 2

    def comparability_warnings(self) -> list[str]:
        """
        Reasons this set may not be a fair fight.

        Returned rather than raised: a flawed set is still worth storing, it just
        should not be pooled with clean ones without a second thought.
        """
        warns: list[str] = []
        if len(self.outcomes) < 2:
            warns.append("Fewer than two variants — nothing to compare.")
            return warns

        ctx = [o.exposure for o in self.outcomes]
        for field in ("platform", "format", "audience_key"):
            vals = {getattr(c, field) for c in ctx if getattr(c, field)}
            if len(vals) > 1:
                warns.append(
                    f"Variants differ on {field} ({sorted(vals)}) — "
                    "this compares conditions, not creative."
                )

        spends = [c.spend_usd for c in ctx if c.spend_usd]
        if spends and min(spends) > 0 and max(spends) / min(spends) > MAX_SPEND_RATIO:
            warns.append(
                f"Spend varies {max(spends) / min(spends):.1f}x across variants "
                f"(> {MAX_SPEND_RATIO}x) — the winner may simply be the funded one."
            )

        sources = {o.source for o in self.outcomes}
        if "ad_library" in sources and len(sources) > 1:
            warns.append(
                "Mixes ad-library observations with reported outcomes — "
                "ad-library sampling has no losers in it."
            )
        return warns

    def ranked_variant_ids(self) -> list[str]:
        """Observed order, best first. The ground-truth ordering a ranker is scored against."""
        scored = [(o.rank_value(), o.outcome_id) for o in self.outcomes if o.rank_value() is not None]
        return [oid for _, oid in sorted(scored, key=lambda p: (-p[0], p[1]))]


class OutcomeCorpus(BaseModel):
    """A file of comparison sets, plus whatever provenance the loader can state."""

    schema_version: str = SCHEMA_VERSION
    generated_at: date | None = None
    note: str = ""
    sets: list[ComparisonSet] = Field(default_factory=list)

    def rankable_sets(self) -> list[ComparisonSet]:
        return [s for s in self.sets if s.is_rankable]

    def summary(self) -> dict[str, Any]:
        rankable = self.rankable_sets()
        flagged = [s for s in rankable if s.comparability_warnings()]
        by_source: dict[str, int] = {}
        for s in self.sets:
            for o in s.outcomes:
                by_source[o.source] = by_source.get(o.source, 0) + 1
        return {
            "sets": len(self.sets),
            "rankable_sets": len(rankable),
            "sets_with_warnings": len(flagged),
            "outcomes": sum(len(s.outcomes) for s in self.sets),
            "outcomes_by_source": by_source,
            "campaigns": len({s.campaign_id for s in self.sets}),
        }
