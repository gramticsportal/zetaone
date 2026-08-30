# Deterministic engine — first held-out baseline

**Date:** 2026-08-23 · **Engine:** hybrid lexical, 54 approved pattern packs · **Runner:** `scripts/eval_hybrid_local.py`

Supersedes the protocol used in `DETERMINISTIC_ENGINE_BENCHMARK_MAIN.md` and
`DETERMINISTIC_ENGINE_MAIN_SYNC.md`, which scored on every eval row that existed. Those
numbers are not wrong, they are **in-sample**, and this document exists to say so
precisely and to record the first figures measured on rows the engine was not tuned
against.

---

## 1. What changed about measurement

Before, every harvested row carried `split: test` and nothing read the field. Mining
tokenised non-compliant rows straight into `forbidden_terms`, so the packs had seen the
rows they were then scored on.

Splits are now assigned by **source enforcement action**, not by row
(`ontology/tools/build_eval_splits.py`). Two leaks made that necessary:

- 1,589 harvested rows come from only **827 cases**; TurboTax alone supplies 27, and rows
  from one case repeat the same claim wording.
- Every compliant row is a rewrite of one specific violation, so a row-level split puts a
  claim in train and its near-twin in test.

| Split | Groups | Rows |
|-------|--------|------|
| train | 578 | 1,869 |
| dev | 121 | 386 |
| test | 128 | 493 |

**13 of the 44 expert precedent cases also appear in the harvested set** and are locked to
test, so training on a harvested sibling cannot contaminate the north star.

---

## 2. Baseline on `test`

Lexical only, NLP off, 688 rows (493 harvested/pairs + 151 seed + 44 precedents).

| Metric | Value |
|--------|-------|
| Precision | **0.824** |
| Recall | **0.595** |
| F1 | **0.691** |
| Specificity | 0.700 |
| Latency | ~5 ms/row |

Per source file:

| File | n (NC) | Recall | n (C) | Specificity |
|------|--------|--------|-------|-------------|
| `eval_precedents.yaml` (north star) | 44 | 0.932 | — | — |
| `eval_harvested.yaml` | 314 | 0.497 | — | — |
| `eval_seed.yaml` | 123 | 0.732 | 24 | 0.292 |
| `eval_compliant_pairs.yaml` | — | — | 179 | 0.754 |

**The 0.932 is still in-sample.** `mine_pattern_candidates.py` read
`eval_precedents.yaml` and tokenised its content into pack terms, so the north star was a
tuning input. The honest reading of this table is the **0.497 on harvested rows** — real
wording from enforcement documents, most of which the miner never saw — against 0.932 on
rows it memorised. That gap is the size of the contamination.

Mining now reads `train` only and refuses `test` by construction, so re-mining the packs
makes these numbers clean. It has **not** been re-run here: it would overwrite the
hand-curated qualifier work from the August matcher rebuild, which is a deliberate
decision rather than a regeneration.

Enabling the NLP scorer changes nothing (identical confusion matrix, 16× slower). It is
correctly left off.

---

## 3. Confidence is now measured, not assumed

`ontology/tools/calibrate_pack_confidence.py` scores each (pack, matcher) on `dev` and
writes `ontology/patterns/confidence.yaml`. The shipped constants — 0.92 phrase, 0.88
regex, 0.72 term for all 54 packs — do not survive contact with the data:

| Pack | Matcher | Hits | Correct | Shipped | Measured |
|------|---------|------|---------|---------|----------|
| `health.unsubstantiated_health_claims` | regex | 29 | 0 | 0.88 | 0.190 |
| `finance.crypto_restricted` | term | 15 | 0 | 0.72 | 0.250 |
| `misleading.unsubstantiated_objective_claims` | regex | 72 | 44 | 0.88 | 0.638 |
| `misleading.exaggerated_results` | phrase | 8 | 7 | 0.92 | 0.897 |

A regex that fires 29 times and is right on none of them shipped at the same confidence as
one that is right 61% of the time.

`ZATAONE_HYBRID_MIN_CONFIDENCE` gates on the measured value. Default 0 (off), because F1
peaks there:

| Threshold | P | R | F1 | Specificity |
|-----------|---|---|----|-----------|
| 0 (default) | 0.824 | 0.595 | **0.691** | 0.700 |
| 0.4 | 0.841 | 0.551 | 0.666 | 0.754 |
| 0.5 | 0.840 | 0.501 | 0.628 | 0.773 |
| 0.6 | 0.858 | 0.401 | 0.547 | 0.842 |
| 0.7 | 0.829 | 0.131 | 0.226 | 0.936 |

It is a reviewer-load dial, not a free win: specificity 0.700 → 0.842 costs 19 points of
recall. Consistent with the existing position that a missed violation costs more than a
flagged one, it stays off by default.

---

## 4. Other changes affecting the deterministic tier

- **Obfuscation.** Matching now runs on normalised text: homoglyphs, digit substitution,
  injected separators, zero-width padding. Spans map back so evidence still quotes the ad
  as published. Disclaimers fold *lightly* on purpose — `results m4y v4ry` must not buy a
  defence, because obfuscated small print is not clear and conspicuous. ~26% latency cost.
- **Absolute packs.** All 18 packs without qualifier classes now carry a stated reason;
  the loader warns on any pack that is neither licensed nor declared absolute. One,
  `atc.tobacco_advertising_format_restrictions`, is recorded as *unmodelled*: 21 CFR
  1140.32 constrains presentation, which lexical matching cannot express.
- **Structural predicates.** The qualifier gate can now be satisfied by a value rather
  than a word. `credit_terms_disclosure` requires a numeric APR, so "ask about our low
  APR!" no longer licenses a credit ad. No measurable effect on this eval — `test` holds
  few credit-disclosure rows — but the rule is now the rule.
- **Priority.** The `priority` already on all 137 corpus rules now reaches the matcher.
  Violations sort most-authoritative first, so an FTC finding (95) leads a platform
  guideline (54–72) on the same creative.

---

## 5. The learned tier, measured on the same holdout

`ontology/tools/train_semantic_classifier.py` trains a linear model on `train`, tunes its
threshold on `dev`, and never reads `test`. It is numpy-only, 242 KB on disk, and its
training is reproducible bit for bit. Scored with `scripts/eval_cascade.py --split test`:

| Configuration | P | R | F1 | F2 | Specificity |
|---|---|---|---|---|---|
| deterministic only | 0.826 | 0.593 | 0.690 | 0.628 | 0.704 |
| semantic only | 0.828 | 0.869 | 0.848 | 0.860 | 0.571 |
| **cascade (det or sem)** | 0.799 | **0.942** | 0.865 | **0.909** | 0.438 |
| confirmed (det and sem) | **0.883** | 0.520 | 0.654 | 0.566 | **0.837** |

Where tier 1 is silent (339 of 684 rows), tier 2 recovers **86%** of the violations it
missed and false-alarms on **38%** of the copy it correctly cleared. Recall 0.593 → 0.942
is real; specificity 0.704 → 0.438 is the price, and in a review-queue deployment that is
reviewer time, so the flag defaults to off.

**Do not read the headline as "the model beats the rules."** Broken out by source:

| Source | det recall | sem recall | sem specificity |
|---|---|---|---|
| `eval_harvested.yaml` | 0.490 | 0.908 | — |
| `eval_precedents.yaml` | 0.932 | 0.864 | — |
| `eval_seed.yaml` | 0.732 | 0.772 | 0.625 |
| `eval_compliant_pairs.yaml` | — | — | **0.564** |

On the compliant minimal pairs — rows built to share their violation's vocabulary — the
model scores 0.564, barely above the 0.5 of a coin. It has not learned the licensing rule;
it has learned that enforcement-quoted copy reads differently from a model-written rewrite.
The model's own `explain()` says so plainly: the highest-weighted features on escalated
copy are `c: the`, `w:the`. That it generalises at all to the differently-written seed rows
(0.772 versus 0.732) is the encouraging part.

So the qualifier gate remains the discriminative layer, and the learned tier is what it was
scoped to be: a recall net over copy the packs have no rule for. It is wired as a sensor —
`ZATAONE_SEMANTIC_CLASSIFIER=1` — that recommends **human review** and cannot raise a
violation.

## 6. What this baseline says to do next

1. **Re-mine packs on `train`** and re-run this document. Expect the north-star figure to
   fall toward the harvested figure; that drop is the measurement getting honest, not the
   engine getting worse.
2. **Fix or retire the packs measuring near zero.** `health.unsubstantiated_health_claims`
   regex and `finance.crypto_restricted` terms are producing noise with a confident label.
3. **The 6 categories with no real data** — discrimination, political, gambling, IP,
   drugs, alcohol — still rest entirely on synthetic seed rows. Harvested coverage is 93%
   `misleading`.
4. **Seed specificity of 0.292** on test compliant rows is the worst number in the table
   and is not explained by contamination. Worth its own look.
