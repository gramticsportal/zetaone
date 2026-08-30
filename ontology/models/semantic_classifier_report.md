# Semantic classifier — training report

**Date:** 2026-08-23 · trained on `train`, tuned on `dev`, `test` untouched

| Property | Value |
|---|---|
| Train rows | 1944 |
| Dev rows | 544 |
| Features | 20010 (20000 n-gram + structural) |
| L2 | 0.0001 |
| Iterations | 400 (loss 0.6931 -> 0.5091) |

## Dev performance

| Metric | Value |
|---|---|
| AUC | **0.837** |
| Threshold (tuned on dev) | 0.42 |
| Precision | 0.685 |
| Recall | 0.904 |
| F1 | 0.780 |
| TP/FP/TN/FN | 255/117/145/27 |

## The two populations, kept apart

- **Harvested violations** (real enforcement wording): recall **0.949** on 217 rows.
- **Compliant minimal pairs** (built to share the violation's vocabulary): correctly cleared **102/169** (60.4%)

The pair number is the honest test of whether this model learned the rule or the
vocabulary. Pairs share trigger words with their violations by construction, so a
bag-of-words model has almost no signal there — and that is exactly why the
qualifier gate, not this model, remains the discriminative layer.

## Reproducing

```bash
python ontology/tools/train_semantic_classifier.py
```

Zero initialisation, no shuffling, fixed iteration count, vocabulary built by
sorted document frequency: the same split produces the same weights byte for byte.
