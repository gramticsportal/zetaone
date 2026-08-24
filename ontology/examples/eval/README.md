# Eval set

These `eval_*.yaml` files are the labeled evaluation set. `../load_eval.py` is the loader.

Harvest working files are in `../harvest/` and are not eval.

## Splits

The unit of assignment is the **source enforcement action**, not the row. A case and
everything derived from it — the harvested violations and their compliant minimal pairs —
land in exactly one split, because 1,589 harvested rows come from only 827 cases and each
compliant row is a rewrite of one specific violation. Splitting by row would put a claim
in train and its near-twin in test.

The 44 expert-labelled rows in `eval_precedents.yaml` are the north star and stay
test-only. 13 of their cases also appear in the harvested set, so those cases are locked
to test as well.

| Split | Groups | Rows | Use |
|-------|--------|------|-----|
| `train` | 578 | 1,869 | mining triggers, fitting a semantic tier |
| `dev` | 121 | 386 | tuning thresholds, curating packs |
| `test` | 128 | 493 | reporting only — never tune against it |

Rebuild and verify:

```bash
python ontology/tools/build_eval_splits.py            # assign (stable, re-runnable)
python ontology/tools/build_eval_splits.py --check    # no group or duplicate spans splits
```

`eval_splits.yaml` is the generated group→split manifest — do not hand-edit it.

Select a split when loading:

```python
load_eval_examples(splits=["train", "dev"])   # or ZATAONE_EVAL_SPLITS=train,dev
```

Anything that fits, mines or curates should ask for `train`/`dev`. Scoring the packs on
the same rows they were curated against is how `eval_non_compliant_hits` ended up baked
into 52 of the 54 packs, and why the current headline numbers are in-sample.
