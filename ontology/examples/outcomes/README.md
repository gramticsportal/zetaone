# Creative outcomes

What we need to collect before the Virality Index can claim anything.

## Why this exists

`ViralityReviewV2` ships `weights_source: "uniform_prior"` — seven dimensions, equal
weights, nothing fitted. Equal weighting is the right default with no outcome data
(Dawes 1979), but it is not *substantiated*. "Virality Index: 78" is an objective
performance claim, and our own corpus holds advertisers to
`ftc.misleading.reasonable_basis` — an objective claim needs a reasonable basis
before it is made. The same standard applies to us.

This directory is the data contract that earns that basis.

## What we are and are not trying to predict

**Not** "will this go viral." Sharing outcomes are dominated by spend, seeding,
timing, network topology and the platform algorithm — none of which are in the copy.
Salganik, Dodds & Watts (2006) ran identical songs through parallel independent
markets and watched outcomes diverge wildly on path dependence alone. There is a low
ceiling on content-intrinsic prediction and no amount of data lifts it.

**Yes** "of these twelve candidate creatives, which three should we test first."
Relative ranking within a campaign. The bar is beating random ordering, the ceiling
is much higher, and test budget is the scarce resource in paid media — so this is the
version that is both achievable and worth money.

## The unit is the comparison set, not the creative

A `ComparisonSet` is variants that ran **under the same conditions** — one campaign,
one audience, one format, comparable spend. Ranking within that set is close to a
natural experiment: the confounders are held constant, so what is left is the
creative.

One creative with no sibling teaches us almost nothing. Four variants from one ad set
teach us a great deal. Collect siblings.

`campaign_id` is also the **split grouping key** — every variant of a campaign lands
in the same train/dev/test split, exactly as every row derived from one enforcement
precedent shares a split in the compliance eval. Splitting variants of one campaign
across train and test leaks the answer.

## Three ways to poison this dataset

The schema flags all three via `ComparisonSet.comparability_warnings()`. They are
flagged rather than rejected — a flawed set is still worth storing, it just must not
be pooled with clean ones without a second thought.

| Trap | What it teaches the model instead | Guard |
|---|---|---|
| **Unequal spend** | who had budget | spend ratio > 3× |
| **Survivorship** (scraped "top ads" galleries contain no losers) | that everything works | `source: ad_library` pooled with reported |
| **Mismatched conditions** | which placement wins | platform / format / `audience_key` differ |

Counts are never stored as outcomes — only rates. Raw shares and impressions encode
spend, which is exactly the confounder we are removing.

## Coarse outcomes are first-class

A design partner will say *"the second one did best"* long before they hand over CPM.
`relative_grade` (`underperformed` / `on_par` / `outperformed`) is enough to fit a
ranker, and nothing in the schema requires numbers we will never be given. Precise
rates are preferred when available; `rank_value()` picks whichever is present and
trustworthy, discarding rates measured over fewer than 1,000 impressions.

## Files

| File | What it is |
|---|---|
| `outcomes_seed.json` | **Synthetic. Illustrative shapes only — do not fit anything on it.** Five sets: one clean four-way test, one coarse partner report, and three deliberately broken ones so loaders and fitters have something to reject. |

## Running the eval

```bash
python scripts/eval_virality_ranking.py --outcomes ontology/examples/outcomes/outcomes_seed.json
```

Reports Spearman's rho between predicted and observed ordering per set, and — the
part that matters — where that lands against a permutation null. With three variants
there are only six possible orderings and a third correlate positively by luck, so a
respectable-looking rho means nothing without the shuffle baseline. If the Index
cannot beat a shuffle, it is not a ranker, whatever its average rho.

On the seed file it scores the two clean sets, skips the two flagged as unfair
fights, drops the single-variant set as unrankable, and then refuses to draw a
conclusion because two sets is nowhere near enough. That last refusal is the point:

```
Scored 2 set(s); skipped 2 flagged as unfair fights.
  cmp.northwind.spring_sleep_2026    n=4  rho=+0.316  beats 68% of shuffles
  cmp.harbourgoods.q3_launch_2026    n=3  rho=+0.866  beats 66% of shuffles
  mean rho +0.5911 · mean percentile vs null 66.8%
  NOTE: 2 sets is far too few to conclude anything.
```

A mean rho of +0.59 looks encouraging and means nothing — the sets are synthetic and
there are two of them. Treat this as a plumbing check.

## How to actually get data

1. **Design partners.** PolicyLens already sees the creative at review time. What is
   missing is a callback ~30 days later. Even the coarse three-way answer is enough.
   Trade a free tier for it.
2. **Meta Ad Library.** Public, and — unlike "top ads" galleries — it contains ads
   that stopped running quickly, which is a usable proxy for the losers.
3. **Existing A/B history.** Any advertiser already running creative tests has
   matched-pairs data sitting unused in their ad account.

## When the weights can change

Not before ~20 rankable clean sets, and not before the Index beats the permutation
null on held-out campaigns. At that point `weights_source` moves off `uniform_prior`
to something fitted and the number becomes defensible. Until then the honest product
is the **dimension-level critique**, not the total.
