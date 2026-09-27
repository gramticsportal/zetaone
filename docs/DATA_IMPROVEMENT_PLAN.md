# Eval data improvement plan

The review models are now limited more by the labelled data than by the model. This
page records what the data looks like, what has been built to improve it, and what
still needs a person or a decision. Current numbers are in
[`ontology/examples/DATA_QUALITY.md`](../ontology/examples/DATA_QUALITY.md)
(regenerate with `ontology/tools/data_quality_report.py`).

## Findings (2026-09-27)

- **3,343 labelled rows, but the LLM eval used 114.** It was limited to rows with a
  saved Gemini answer. `scripts/eval_local_review.py` now runs without a baseline, so
  the local model and matcher can be scored on the whole corpus.
- **82% of labels are model-made.** 2,729 rows are sentences harvested from enforcement
  documents plus AI-written compliant rewrites; 614 are expert rows.
- **Fragments labelled as violations.** 216 violations are under 30 characters
  ("releases a moisturizing lotion"): the case was a violation, the sentence alone
  often is not.
- **Hedge-only compliant pairs.** 52% of the compliant rewrites (596) differ from the
  violation only by a qualifier ("for many users"), which teaches that a hedge makes a
  claim safe, the loophole real advertisers use.
- **No real compliant ads.** Compliant rows are hand-written or rewritten, so models
  never see what approved ads in a regulated category look like: a likely cause of
  false alarms.
- **Thin categories.** Only `misleading` meets 100 rows per label; alcohol has 9
  violations, drugs 15.
- **No platform or non-US labels,** and 93% text: image and video rows are mostly
  bracketed descriptions of the creative.
- **The 114-row eval could not separate models.** With 74 violations the 95% interval
  on recall is about ±7 points. The grouped test split (547 violations) gives ±2.5.

## Done

| Change | Where |
| --- | --- |
| Grouped train/dev/test splits applied (by source case; north star locked to test) | `ontology/tools/build_eval_splits.py`, eval YAMLs |
| Eval runs on the whole corpus, filters by split, records matcher verdict and row metadata | `scripts/eval_local_review.py` |
| Disagreement audit queue in the existing gold-review CSV format | `ontology/tools/build_disagreement_queue.py` → `ontology/examples/harvest/eval_disagreement_review.csv` |
| Data-quality report | `ontology/tools/data_quality_report.py` → `ontology/examples/DATA_QUALITY.md` |
| Blind double-labelling sample and Cohen's kappa | `ontology/tools/agreement_study.py` |
| Rich-label sidecar (platform, decision, severity, evidence spans, policy date) with validator; the frozen example schema is untouched | `ontology/examples/annotations/`, `ontology/tools/validate_annotations.py` |
| Shadow mode: local review stored beside Gemini's on real traffic, with would-escalate reason | `ZATAONE_REVIEW_SHADOW=1` |

## Needs a person or a decision

1. **Work the audit queue.** Fill `human_decision` in
   `eval_disagreement_review.csv`, starting with `high` rows flagged `fragment` or
   `hedge_only_pair`, then apply with
   `apply_eval_gold_decisions.py --csv ontology/examples/harvest/eval_disagreement_review.csv --apply`.
   The systems are advisory; nothing is relabelled automatically.
2. **Run the agreement study.** Two reviewers label the same 200-row blind sample
   (`agreement_study.py sample --n 200`); score with `agreement_study.py score`. The
   kappa is the realistic ceiling for any model.
3. **Decide on real compliant ads.** Public ad libraries (Meta Ad Library, Google Ads
   Transparency Center) show ads that ran. Collecting from them needs a terms-of-use
   and API-access decision before any tooling is built. Target a few hundred per
   regulated category.
4. **Fill thin categories** to at least 100 violations and 100 compliant rows each,
   starting with the beachhead vertical.
5. **Resolve the 190 borderline rows** into compliant / non_compliant with a clause,
   or keep them as an explicit third class with its own metric.
6. **Turn on shadow mode** where Gemini already runs, and record reviewer and platform
   decisions through `POST /assets/{asset_id}/review` (`human_review`, `appeal`,
   `platform_feedback`). A few hundred real outcomes are worth more than all the
   synthetic rows, and they are what a later fine-tune of the local model needs.
7. **Gemini key for the corpus baseline.** Cascade scores on the full corpus need the
   Gemini answer for the ~36% of rows it escalates (about 1,100 calls).
