# Eval set

These `eval_*.yaml` files are the labeled evaluation set. `../load_eval.py` is the loader.

Harvest working files are in `../harvest/` and are not eval.

## Splits

**Current policy:** every labeled row is in the **eval set** (`split: test`). There is no
active train/dev partition — score the full corpus, then drop low-quality rows later.

**Score it:** from repo root, `PYTHONPATH=src python3.11 scripts/eval_matcher.py` (full corpus + pairs, NLP off).

`../load_eval.py` loads seed + precedents + harvested + compliant pairs by default.
Set `ZATAONE_EVAL_INCLUDE_HARVESTED=0` to drop harvest/pairs. Optional
`ZATAONE_EVAL_SPLITS=…` still filters if you need it.

`build_eval_splits.py` / `eval_splits.yaml` remain for if you reintroduce a holdout later.
Do not treat them as the live reporting protocol right now.

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
