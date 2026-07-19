# ZataOne deterministic engine — main-branch benchmark report

**Date:** 2026-07-19 · **Repo:** `main` @ `2dc5c87` · **Engine:** corpus-built `PolicyEngine` (121 rules) · **Runner:** `scripts/eval_policy_engine.py`

Companion to *DETERMINISTIC_ENGINE_COFOUNDER_SYNC* (hybrid lexical, `af34b52`). Same eval files, same protocol, so the two scoreboards compare directly.

---

## 1. What was measured

| Piece | This report | Cofounder sync |
| :---- | :---- | :---- |
| Engine | `PolicyEngine` + DSL (phrase/term/regex, context & exception gates) | Hybrid lexical (pattern packs) |
| Rule source | `ontology/corpus/*_us.yaml` → `ontology_rule_builder` (121 rules) | `ontology/patterns/by_category/*.yaml` (52 packs) |
| Term mining | Naive: clause text tokenized to ≤20 single terms + category seeds | Phase A mined phrase packs w/ context gates |
| ML / NLP in loop | **None** (SemanticTextExtractor exists but is supporting-evidence-only, cannot flip a verdict) | NLP off (demoted) |
| Path exercised | Full deterministic core: TextExtractor → DocumentBuilder → PolicyEngine | Pack matcher on `content` |

**Protocol (identical to sync doc §4):** examples from `ontology/examples/eval_seed.yaml` (570) + `eval_precedents.yaml` (44); positive = ≥1 violation on text `content`; no VLM/OCR/LLM in the metrics; 44-recall always reported.

> **Context that matters:** until `main @ cb16737` (2026-07-19), `vision_primary_labels` on 105/121 corpus rules suppressed *all* deterministic text matches — this engine would have scored **0.000** on every metric below. These are its first valid numbers.

---

## 2. Head-to-head scoreboard

| Metric | **PolicyEngine (main)** | **Hybrid lexical (cofounder)** | Winner |
| :---- | :---- | :---- | :---- |
| **44-precedent recall (north star)** | **0.455** (20/44) | **0.818** (36/44) | hybrid |
| Clean seed+prec (424) — F1 | 0.394 | 0.634 | hybrid |
| Clean seed+prec — precision | **0.733** | 0.554 | **main** |
| Clean seed+prec — recall | 0.269 | 0.739 | hybrid |
| Seed NC+C (380) — P / R / F1 | 0.652 / 0.226 / 0.336 | ≈ same as clean | hybrid |
| Borderline positive rate | 0.105 (20/190) | n/r | — |
| Latency (text, local) | ~45 ms/ex (full extractor stack) | ~0.2–5 ms/ex (matcher only) | hybrid |

**Read:** the two engines have opposite failure modes. Main is a *precise under-firer* (flags less, but is right 73% of the time). Hybrid is a *recall machine* that over-fires (55% precision). For compliance, recall is the more valuable side — a missed violation costs more than a flagged-for-review FP.

---

## 3. Per-category breakdown (main engine, seed NC+C)

| Category | NC recall | Compliant FP rate | Verdict |
| :---- | :---- | :---- | :---- |
| health | **0.80** (16/20) | 0.10 | strong — hand-tuned keyword heritage |
| misleading | 0.50 (5/10) | 0.14 | mid |
| ip_trademark | 0.35 (7/20) | 0.20 | weak |
| financial | 0.25 (5/20) | 0.25 | weak, noisy |
| privacy | 0.20 (4/20) | 0.20 | weak |
| gambling | 0.15 (3/20) | 0.20 | weak |
| alcohol | 0.14 (1/7) | 0.10 | weak |
| minors | 0.10 (2/20) | 0.00 | near-dead |
| discrimination | **0.00** (0/20) | 0.05 | dead |
| political | **0.00** (0/20) | 0.00 | dead |
| drugs | **0.00** (0/13) | 0.10 | dead |

The dead/weak categories are exactly the ones whose `prohibited_terms` come entirely from naive single-word tokenization in `ontology_rule_builder.py`. Health is strong because it inherits curated term lists. **The recall gap is a term-mining quality gap, not an engine-architecture gap** — the DSL itself (gates, exceptions, spans) is fine and delivers the precision edge.

### Precedents missed (24/44)

`kardashian_emax_2022, paul_pierce_emax_2023, lohan_trx_2023, mayweather_centra_2018, flyfish_nft_2024, robinhood_finfluencer_2025, m1_influencer_2024, moomoo_zero_commission_2024, reebok_easetone_2011, skechers_shapeups_2012, pch_sweepstakes_2023, mckenzie_energy_beer_2007, clean_beer_2022, bountiful_reviews_2023, cameo_celebrity_2024, iheart_pixel_radio_2022, herbalife_mlm_2016, western_benefits_2024, rmk_va_mortgage_2023, att_unlimited_2019, juul_youth_2023, bugaboo_counterfeit_2025, vw_clean_diesel_2016, opendoor_chart_2022`

Heavy overlap with finfluencer/undisclosed-promotion and semantic-claim cases — including the hybrid engine's own 8 FNs (TurboTax/EaseTone class). Those need an NLI/classifier layer, not more terms; the rest are reachable with better packs.

---

## 4. Interpretation & proposed direction

1. **Shortest path to ≥0.818 recall: adopt the 52 approved pattern packs** (`ontology/patterns/`) from the hybrid branch as this engine's term/phrase source, replacing naive tokenization in `ontology_rule_builder`. Same corpus, better mining — a merge, not a research project.
2. **Guard the precision edge.** After adopting packs, re-run this benchmark; if precision drops to ~0.55 we've cloned the hybrid engine instead of beating it. Target: **R ≥ 0.82 with P > 0.65**, using the DSL's context/exception gates as the differentiator.
3. **Shared semantic gap → shared roadmap item.** Both engines miss the same semantic-claim precedents. That is the NLI/category-classifier sensor (sync doc "agreed direction #3" = our phase-1 ML roadmap). Embedding cosine is confirmed dead by both sides' experiments.
4. **Latency note:** the 45 ms/ex includes VADER/langdetect/readability extraction. The matcher itself is sub-ms; extraction can be trimmed or cached if eval speed matters.

---

## 5. Reproduce

```bash
# local (Python 3.10+): PYTHONPATH=src python scripts/eval_policy_engine.py
docker compose exec api python scripts/eval_policy_engine.py
```

Prints engine, rule count, git SHA, all metrics above. Re-run after any corpus, pack, or engine change and record the SHA next to the numbers.

## 6. One-line scoreboard

| North star | Main engine | To beat |
| :---- | :---- | :---- |
| 44-precedent recall | **0.455** | 0.818 |
| Clean seed+prec F1 | **0.394** (P 0.733 / R 0.269) | 0.634 |
