# ZataOne deterministic engine (main) — cofounder sync

**Date:** 2026-07-19 · **Repo:** `main` @ `3f839c4` · **Counterpart doc:** *DETERMINISTIC_ENGINE_COFOUNDER_SYNC* (hybrid, `af34b52`)

---

## 1\. What the deterministic engine is *today*

### Role in the product

- **Deterministic layer** \= audit evidence (violations, risk, evidence graph with char-offset spans).
- **Display verdict** \= hybrid display (advisory LLM annotates; deterministic authoritative when engine runs).
- Same framing as the hybrid doc: "better deterministic" \= **better rule hits vs gold labels**.

### Engine implementation

| Piece | Current default (main) |
| :---- | :---- |
| Engine | **PolicyEngine \+ DSL** (`RuleEvaluator`: phrase → regex → terms, context/exception gates per rule) |
| Rules | **121 rule-level rules** built from `ontology/corpus/*_us.yaml` (clause-mapped, rule-level evidence) |
| Vocabulary | Corpus-mined terms **\+ adopted pattern packs** (`ontology/patterns/`, 52 approved — *data only, no hybrid engine code*) |
| Text view | **Document-centric ON** (`ZATAONE_DOCUMENT_CENTRIC=1`) — rules match full normalized document text |
| Pack flags | `ZATAONE_PATTERN_PACKS=1`, `ZATAONE_PACK_TERMS=1`; context-gate & replace-terms off |
| Embedding NLP | **OFF** in eval loop (SemanticTextExtractor exists as supporting-evidence sensor only; cannot flip a verdict) |
| Evidence | Full pipeline per example: extractor signals → DocumentBuilder spans → violations with clause ids |

**Decision rule for eval:** any violation → `non_compliant`; none → `compliant`. Identical to hybrid doc.

### Key finding this phase (root cause, not vocabulary)

Default fragment mode matched rules **only against extractor-flagged snippets**, never the full text — the engine could only re-confirm the extractor's own keyword list (political/drugs/discrimination recall \= 0.00). Enabling document-centric matching is worth more than all vocabulary changes combined: F1 0.394 → 0.706 **before** any pack data.

---

## 2\. Corpus vs eval set

| Asset | Location | Notes |
| :---- | :---- | :---- |
| US clauses / rules | `ontology/corpus/*_us.yaml` | Same corpus as hybrid (146 clauses / 121 rules) |
| **Pattern packs (adopted)** | `ontology/patterns/` | Same 52 approved packs as hybrid; consumed by our DSL via `pattern_packs.py` (join on `source_rule_ids`) |
| Eval set | `ontology/examples/eval_seed.yaml` (570) \+ `eval_precedents.yaml` (44) | **Byte-identical to hybrid eval** — no set drift |

**Fairness note (symmetric, both engines):** our rule builder and the hybrid pack miner both drew some vocabulary from the eval examples. Head-to-head stays fair; absolute numbers are inflated. Do not quote externally until the seed denoise (hybrid doc §5.4) is done.

---

## 3\. Experiments & results (deterministic only)

All numbers \= local text `content`, no Gemini, no OCR/DINO, no LLM.

### Setup that won

- Document-centric matching \+ packs merged \+ pack terms on
- Binary: ignore borderline unless noted; positive \= ≥1 violation

### Headline results

| Experiment | Set | Precision | Recall | F1 | Notes |
| :---- | :---- | :---- | :---- | :---- | :---- |
| Baseline (fragment mode, pre-fix) | Clean 424 | 0.733 | 0.269 | 0.394 | Rules never saw full text |
| Doc-centric, no packs | Clean 424 | 0.550 | 0.983 | 0.706 | **The flag is the story** |
| Packs phrases-only (naive terms removed) | Clean 424 | 0.580 | 0.201 | 0.298 | Phrases alone are weak — for both engines |
| **Doc-centric \+ packs \+ terms (shipped)** | Clean 424 | **0.554** | **0.991** | **0.711** | Best F1 |
| Same | **44 golden** | N/A (no C) | **0.977** | — | **43/44** detected |
| *Hybrid reference (their doc)* | Clean 424 | *0.554* | *0.739* | *0.634* | — |
| *Hybrid reference* | *44 golden* | — | *0.818* | — | *36/44* |

**Latency (local text):** \~45 ms/example — but that is the **full pipeline** (extraction \+ document \+ evidence spans), not a bare matcher (hybrid: 0.2–5 ms matcher-only). We outperform while producing audit-grade evidence per hit.

### 44 golden — 1 FN remaining

Semantic-claim class (no lexical surface) — same family as the hybrid's 8 FNs. Classifier territory, not vocabulary.

### The precision wall (most important shared finding)

**Both engines converge to P ≈ 0.554 at high recall.** Compliant seed rows are in-category copy; single category terms ("beer", "casino", "loan") fire on them regardless of compliance. More lexicon cannot move precision. Levers that can: multi-hit / severity-weighted decision rule, real context gating (pack gates are wired but off — hard-gating costs recall), NLI/category classifier on the shortlist.

---

## 4\. How to run the same experiments (apples-to-apples)

```bash
# shipped config (doc-centric + packs + terms) is docker-compose default:
docker compose exec api python scripts/eval_policy_engine.py

# ablations via env flags:
#   ZATAONE_DOCUMENT_CENTRIC=0     fragment mode (old baseline)
#   ZATAONE_PATTERN_PACKS=0        drop pack vocabulary
#   ZATAONE_PACK_TERMS=0           phrases/regex only
#   ZATAONE_PACK_REPLACE_TERMS=1   pack vocab replaces naive terms
#   ZATAONE_PACK_CONTEXT_GATE=1    pack context as hard gate
```

Runner loads the same eval files via `ontology/examples/load_eval.py`, prints rule count \+ SHA next to metrics. Protocol per hybrid doc §4 (same files, same positive definition, text-only, 44-recall always reported).

---

## 5\. Proposed direction

1. **Adopt document-centric matching as the default** (currently env-gated; on in local compose). Decide production rollout together — it changes evidence spans and verdict volume.
2. **Converge on one engine:** DSL \+ rule-level evidence consuming the shared packs beat the pack-cascade matcher on the same data (F1 0.711 vs 0.634, recall 0.977 vs 0.818, equal precision). Proposal: hybrid branch's *miner* stays (it produces the packs), the *runtime matcher* consolidates on PolicyEngine.
3. **Attack the 0.554 precision wall jointly** — decision-rule experiments (≥2 distinct rules, severity weighting) \+ NLI/category classifier for the semantic FNs (\= hybrid doc "agreed direction \#3").
4. **Denoise the seed set before any external numbers** (both engines train-on-test today; both scoreboards inflated symmetrically).
5. Re-run `scripts/eval_policy_engine.py` after any corpus/pack/engine change; record SHA next to metrics.

---

## 6\. One-line scoreboard

| North-star | Main (this doc) | Hybrid (their doc) |
| :---- | :---- | :---- |
| **44-precedent recall** | **0.977** (43/44) | 0.818 (36/44) |
| **Clean seed+prec F1** | **0.711** (P 0.554 / R 0.991) | 0.634 (P 0.554 / R 0.739) |

Bar their doc set: *"beat 0.818 recall on the 44 without collapsing precision on seed compliant rows"* — met: recall 0.977 at identical precision (0.554). Detailed ablation history: `docs/DETERMINISTIC_ENGINE_BENCHMARK_MAIN.md`.
