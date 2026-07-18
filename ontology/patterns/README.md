# Hybrid pattern packs (Phase A)

Corpus-mined **hierarchical hybrid matchers** for the US ontology.

```
category_id
  └── canonical_id   ← one pattern pack (universal rule)
        ├── source_rule_ids / clause_ids
        ├── forbidden_terms / phrases / regex
        ├── requires_context
        ├── exceptions
        ├── vision_labels (+ min confidence)
        └── embedding_prototypes (detection summaries)
```

## Files

| Path | Purpose |
|------|---------|
| `schema.yaml` | Pattern-pack field definitions |
| `_inventory.yaml` | Counts + canonical index (all packs) |
| `by_category/<category>.yaml` | Full packs grouped by category |
| `candidates_review.csv` | Spreadsheet for founder curation |
| `../tools/mine_pattern_candidates.py` | Regenerator |

## Regenerating + QC approve

```bash
python ontology/tools/mine_pattern_candidates.py
python ontology/tools/curate_and_approve_patterns.py
```

Inputs: `ontology/corpus/*_us.yaml`, `examples/eval_*.yaml`, optional `tools/vision_queries_mined.yaml`.

**QC (2026-07-15):** all **52** packs `approved` after denoise + smoke tests (7/7).  
Political `vision_min_confidence` raised to **0.65**. Academic-slide FP case no longer phrase/regex-hits political/misleading.

## Review status

| Status | Meaning |
|--------|---------|
| `mined` | Auto-generated (pre-QC) |
| `curated` | Cleaned but terms-only (weak) |
| `approved` | Ready for Phase B hybrid engine (**current**) |
| `deprecated` | Do not load at runtime |

## Runtime note (Phase B)

- **Offline:** mine whole corpus (this folder).
- **Online:** BM25 shortlist → evaluate packs for shortlisted `canonical_id`s only.
- Do not treat mined packs as production-ready until curated (regex FP risk).

## Phase B (wired)

Hybrid engine: `src/zataone/policy_engine/hybrid/`

| Flag | Default | Meaning |
|------|---------|---------|
| `ZATAONE_HYBRID_ENGINE` | **ON** | Replace legacy PolicyEngine with hybrid |
| `ZATAONE_HYBRID_NLP` | **OFF** | Embedding NLP scorer (demoted; lexical primary) |
| `ZATAONE_HYBRID_NLP_BACKEND` | `auto` | `auto` \| `minilm` \| `bow` \| `bge_small` \| `e5_small` |
| `ZATAONE_HYBRID_ALL_PACKS` | **ON** | Evaluate all approved packs (no shortlist) |
| `ZATAONE_HYBRID_RETRIEVAL_TOP_K` | 32 | Under-filter BM25 shortlist |

Rollback: `ZATAONE_HYBRID_ENGINE=0` (legacy engine).
