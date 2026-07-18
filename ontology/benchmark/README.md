# Benchmark suite — retrieval tests + coverage statistics.

## Commands

```bash
# Referential integrity + sidecars (precedents, policy_timeline, policy_versions)
python ontology/validate.py

# Coverage by domain, platform, jurisdiction, canonical rule
python ontology/benchmark/coverage.py
python ontology/benchmark/coverage.py --json

# Keyword retrieval baseline (must-include clause/category/canonical in top_k)
python ontology/benchmark/run_retrieval_tests.py

# Regenerate per-clause policy diff timeline from corpus + policy_versions
python ontology/tools/build_policy_timeline.py
```

## Files

| File | Purpose |
|------|---------|
| `retrieval_tests.yaml` | Labeled queries with required hits in top_k |
| `run_retrieval_tests.py` | Runs token-overlap retrieval benchmark |
| `coverage.py` | Reports corpus/precedent/eval gaps (seed + precedent eval files) |

## Coverage dimensions

- **Domain** — clauses/evals/precedents per `category_id`
- **Platform** — clauses per platform `source_id`
- **Jurisdiction** — clauses per `jurisdiction` code (US, EU, UK, CA, AU)
- **Canonical rule** — cross-source vs single-source mappings; precedent linkage gaps

Target over time: precedents in the **hundreds** (official enforcement only), full
vertical depth per jurisdiction/platform, and embedding-based retrieval benchmarks
alongside this keyword baseline.
