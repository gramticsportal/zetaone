# Eval set

These `eval_*.yaml` files are the labeled evaluation set. `../load_eval.py` is the loader.

Harvest working files are in `../harvest/` and are not eval.

## Splits

**Current policy:** every labeled row is in the **eval set** (`split: test`). There is no
active train/dev partition — score the full corpus, then drop low-quality rows later.

`../load_eval.py` loads seed + precedents + harvested + compliant pairs by default.
Set `ZATAONE_EVAL_INCLUDE_HARVESTED=0` to drop harvest/pairs. Optional
`ZATAONE_EVAL_SPLITS=…` still filters if you need it.

`build_eval_splits.py` / `eval_splits.yaml` remain for if you reintroduce a holdout later.
Do not treat them as the live reporting protocol right now.
