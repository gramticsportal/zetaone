# Eval set

These `eval_*.yaml` files are the labeled evaluation set. `../load_eval.py` is the loader.

Harvest working files are in `../harvest/` and are not eval.

## Splits

**Current policy (2026-09-27):** harvested rows and their compliant minimal pairs carry
`train` / `dev` / `test` from `../../tools/build_eval_splits.py`, grouped by source
enforcement case so a violation and its rewrite never straddle splits. Expert seed rows
and the 44 precedents are all `test` (the north star), and cases shared with a
precedent are locked to test.

The loader still returns **every row** by default, so existing scores do not change.
Filter with `ZATAONE_EVAL_SPLITS=test` (or `eval_local_review.py --split test`) to
report on held-out rows; tune gates, prompts and thresholds on `train`/`dev` only.

```bash
python3.11 ontology/tools/build_eval_splits.py --check   # after adding rows
```

**Score it:** from repo root, `PYTHONPATH=src python3.11 scripts/eval_matcher.py` (full corpus + pairs, NLP off).

## Data quality and label audit tools

| Tool | What it does |
| --- | --- |
| `data_quality_report.py` | Coverage by category, labeller, modality and split, error bars, label hazards → `../DATA_QUALITY.md` |
| `build_disagreement_queue.py RUN.json` | Queues rows where the matcher, local model (and Gemini) disagree with gold → `../harvest/eval_disagreement_review.csv`; apply with `apply_eval_gold_decisions.py --csv …` |
| `agreement_study.py sample / score` | Blind double-labelling sample and Cohen's kappa: the ceiling for any model |
| `validate_annotations.py` | Checks `../annotations/annotations.yaml` (platform, decision, severity, evidence spans, policy date) |

## Gold audit (make the labels perfect)

Goal: separate **matcher bugs** from **bad gold**. Review high-priority rows first.

### 1. Build the review queue (matcher tags + optional Gemini justification)

```bash
# Fast queue only — FN/FP/short ads, no API
PYTHONPATH=src python3.11 ontology/tools/audit_eval_gold.py --priority high --limit 100

# With Gemini reasons (set GEMINI_API_KEY). Speeds human review.
PYTHONPATH=src python3.11 ontology/tools/audit_eval_gold.py --gemini --priority high --limit 50
```

Writes:

- `../harvest/eval_gold_review.csv` — fill `human_decision`
- `../harvest/eval_gold_review.html` — browser-friendly view

Columns to trust in order: `error_type` (FN/FP) → `gemini_label_agree` / `gemini_reason` → your call.

`human_decision` values: `keep` | `drop` | `relabel_nc` | `relabel_c` | `quarantine`

```bash
python3.11 ontology/tools/apply_eval_gold_decisions.py          # dry-run
python3.11 ontology/tools/apply_eval_gold_decisions.py --apply  # write YAMLs
```

### 2. Harvest quality (assessable vs junk extraction)

```bash
PYTHONPATH=src python3.11 ontology/tools/audit_missed_violations.py --limit 200   # or full
PYTHONPATH=src python3.11 ontology/tools/quarantine_harvest_junk.py             # after you trust the CSV
```

`audit_missed_violations.py` labels `assessable_claim` / `fragment` / `not_a_claim` with a Gemini reason. Quarantine moves junk (and twin pairs) out of eval into `../harvest/`.

### 3. Review order that stays honest

1. **High priority FN** where Gemini says `fragment` / `not_a_claim` / `disagree` → drop or relabel (don’t credit the matcher).
2. **High priority FP** where Gemini `agree` with compliant → pack false alarm (fix packs / gates).
3. **High priority FN** where Gemini `agree` with non_compliant → real miss → mine triggers (`mine_fn_triggers.py`).
4. Only then touch medium/low priority rows.

Gemini is **advisory**. Precedents stay expert-owned; never bulk-accept model labels into gold without a human tick.

### 4. Mine triggers from remaining true FNs

```bash
PYTHONPATH=src python3.11 ontology/tools/mine_fn_triggers.py
# → ontology/patterns/candidates_fn_review.csv — hand-add phrases to packs
```
