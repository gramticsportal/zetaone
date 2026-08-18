# ZataOne deterministic engine — cofounder sync

**Date:** 2026-07-18 · **Repo:** `main` @ `af34b52` · **Live API:** Cloud Run `zataone-api` (`vlm-primary-20260718-130341`)

---

## 1. What the deterministic engine is *today*

### Role in the product

- **Deterministic layer** = audit evidence (violations, risk, explainability graph).
- **Display verdict** = still **LLM** (`ZATAONE_VERDICT_AUTHORITY=advisory` by default).
- So “better deterministic” means **better rule hits vs gold labels**, not necessarily better UI labels.

### Engine implementation

| Piece | Current default |
|--------|-----------------|
| Engine | **Hybrid lexical** (`ZATAONE_HYBRID_ENGINE=1`) |
| Matchers | **Phrase → regex → terms** (+ context / exception gates) |
| Pattern packs | `ontology/patterns/by_category/*.yaml` — **52 approved** packs mined from US corpus (Phase A) |
| Embedding NLP (BoW / MiniLM / BGE / E5) | **OFF** (`ZATAONE_HYBRID_NLP=0`) — demoted; little lift |
| Pack coverage | **All 52 packs** every run (`ZATAONE_HYBRID_ALL_PACKS=1`) |
| Legacy `PolicyEngine` | Fallback if hybrid off / empty packs |

**Decision rule for eval:** any violation → predict `non_compliant`; none → `compliant`. That is what P/R measure.

### Image path (sensors → same engine)

Not part of the text eval loop, but important for product:

1. **Gemini VLM** → structured JSON: `ocr_text`, `ad_claims_text`, `objects[]`, `scene_description`
2. Matcher uses **claims + OCR + objects** (scene mainly for final LLM)
3. **Local OCR + Grounding DINO off** by default
4. Final LLM gets **full VLM packet + deterministic hits**

Text eval / pack comparison should use **example `content` strings only** (hybrid), not Cloud Run image latency.

---

## 2. Corpus vs eval set

### Policy corpus (rules / ontology)

| Asset | Location | Notes |
|--------|----------|--------|
| US clauses / rules | `ontology/corpus/*_us.yaml` | Runtime pack source (~146 clauses / ~121 rules when built) |
| Canonical unifications | `ontology/mappings.yaml` | Cross-platform / regulator |
| **Pattern packs (hybrid)** | `ontology/patterns/` | Derived from corpus + eval mining; **this is what lexical matches** |
| Precedents (enforcement stories) | `ontology/precedents/` | Used to build the 44 golden rows |

**Important:** We did **not** expand the clause corpus in this phase. Phase A mined **pattern packs from the existing corpus**; Phase B wired hybrid to those packs.

### Eval set (two parts)

| Part | File | Size | Labels | Quality |
|------|------|------|--------|---------|
| **A. Golden / precedents** | `ontology/examples/eval_precedents.yaml` | **44** | All `non_compliant` | **High** — tied to real enforcement cases; copy may be reconstructed |
| **B. Synthetic seed** | `ontology/examples/eval_seed.yaml` | **570** | 190 NC / 190 C / 190 borderline | **Noisy** — authored grid by category; `labeled_by: expert` = seed authoring, not multi-reviewed gold |

**Clean convenience filter (not true label denoise):**  
`eval_seed_clean.yaml` = seed **without borderline** (380). Load with `ZATAONE_EVAL_PROFILE=clean`.  
Real denoise should re-review NC/C against `violated_clause_ids` per category — we have not done that yet.

---

## 3. Experiments & results (deterministic / hybrid only)

All numbers below = **local hybrid on text `content`**, no Gemini, no OCR/DINO.

### Setup that won

- Lexical on **all packs**, NLP **off**
- Binary: ignore borderline unless noted
- Positive = ≥1 violation

### Headline results

| Experiment | Set | Precision | Recall | F1 | Notes |
|------------|-----|-----------|--------|-----|--------|
| Current hybrid (shortlist + NLP, early) | Full 614 | ~0.56 | ~0.59 | ~0.57 | Under-filtered by shortlist |
| **Lexical, all packs, NLP off** | Full 614 | **0.554** | **0.739** | **0.634** | Best full-set F1 we got |
| Same | **44 golden** | N/A (no C) | **0.818** | — | **36/44** detected |
| Same | Clean seed+prec (424) | 0.554 | 0.739 | 0.634 | ≈ full without borderline |
| BoW NLP alone, all packs | Full | weak | — | ~0.02–0.51 | Not viable as main matcher |
| Lexical + BoW | Full | 0.554 | 0.739 | 0.634 | **Same as lexical alone** |
| MiniLM / L12 / BGE / E5 as pack scorers | Full | ~0.55–0.56 | ~0.59–1.0* | ≤0.59 honest | *e5 R=1.0 = over-fire, not a win |

**Latency (local text):** ~0.2–5 ms/example for lexical; neural NLP ~280–800 ms/ex — not worth it for this matcher job.

### 44 golden — what we still miss (8 FNs)

Semantic / policy-shaped cases packs don’t phrase-match well, e.g. TurboTax “free for everyone”, EasyTone toning claims, COVID tea, DraftKings, counterfeit “inspired style”, some finfluencer copy. These are the right targets for **NLI / classifier / LLM**, not more embedding-to-prototype cosine.

### Seed noise signal

Many “FPs” on labeled-compliant seed are **weak pack terms** (`support`, `elect`, `brand`, `guarantee` in disclaimer context) — often **engine false positives**, not wrong gold. So seed P/R understates pack quality issues and overstates “label noise” if you only look at F1.

---

## 4. How to run the same experiments (apples-to-apples)

From repo root:

```bash
# Defaults today: hybrid on, NLP off, all packs on
PYTHONPATH=src python scripts/eval_hybrid_local.py

# Clean seed (no borderline) + precedents
ZATAONE_EVAL_PROFILE=clean PYTHONPATH=src python scripts/eval_hybrid_local.py

# Optional: NLP backend bake-off (we already concluded demote NLP)
PYTHONPATH=src python scripts/eval_hybrid_compare_nlp.py --backends bow,minilm,bge_small
```

**Minimal custom loop (recommended for comparing another engine):**

1. Load examples via `ontology/examples/load_eval.py` (`ZATAONE_EVAL_PROFILE=full|clean`).
2. For each example, run **your** deterministic function on `content` → bool or violation list.
3. Report **separately**:
   - **Recall on 44 precedents** (north-star)
   - **P / R / F1 on seed NC+C** (or clean profile)
   - Optional: borderline hit-rate
4. Do **not** mix LLM display verdict into these metrics.

**Compare fairly:**

| Must match | Why |
|------------|-----|
| Same eval files / profile | Avoid silent set drift |
| Same positive definition (≥1 hit) | Or document if you use category-conditional hits |
| Text-only `content` | Don’t require VLM unless comparing image sensors |
| Report 44 recall **always** | Seed alone is too noisy to declare a winner |

**If you change packs or corpus:** regenerate or version packs; note pack count + git SHA next to metrics.

---

## 5. Agreed direction (so experiments stay aligned)

1. Keep **lexical packs** as the fast primary deterministic matcher.
2. Do **not** invest in embedding NLP as the main matcher.
3. Next semantic layer: **NLI / category classifier** (or LLM on shortlist), aimed at the **8 golden FNs** + financial gaps.
4. **Denoise seed properly** by authoring rubric (category × NC/C/borderline × clauses) before quoting external metrics.
5. Image quality = VLM→text quality; compare that separately from text-pack F1.

---

## 6. One-line scoreboard to beat

| North-star | Current best |
|------------|----------------|
| **44-precedent recall** | **0.818** (36/44), lexical all-packs, NLP off |
| **Full seed+prec F1** (ignore borderline) | **0.634** (P 0.554 / R 0.739) |

If a new deterministic approach beats **0.818 recall on the 44** without collapsing precision on seed compliant rows, it’s a real win.
