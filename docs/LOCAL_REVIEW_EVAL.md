# Local review evaluation

## Result

Qwen3 8B ran locally through Ollama/Metal on all 114 labeled text cases. The
evaluation made no Gemini API calls; Gemini numbers below come from the saved
baseline for the same row IDs.

| Metric | Qwen3 8B local | Saved Gemini baseline |
| --- | ---: | ---: |
| Precision | 75.28% | 81.48% |
| Recall | 90.54% | 89.19% |
| F1 | 82.21% | 85.16% |
| Accuracy | 74.56% | 79.82% |
| High-severity recall | 93.48% | 91.30% |

The high-severity cohort combines HIGH/CRITICAL deterministic matches with
labeled enforcement precedents. Qwen had 3 false negatives in 46 cases versus
Gemini's 4. This satisfies the safety gate of no regression in high-severity
recall, although Qwen is more conservative overall and creates more false
positives.

## Reliability and latency

- Schema-valid output: 100%
- Valid signal citations: 100%
- Missing reviews after retry: 0
- Median local model latency: 19.88 seconds
- Mean local model latency: 21.27 seconds
- Maximum local model latency: 77.50 seconds
- Estimated cascade fallback rate: 0.88%

The initial capped-output run had three missing reviews. Retrying those locally
with the full output allowance completed all 114 cases.

## Recommendation

Use Qwen3 8B as the local-first advisory reviewer behind the implemented
cascade, while the deterministic matcher remains authoritative. Keep Gemini as
fallback for invalid JSON, unclear/divergent assessments, missing verdicts, or
invalid citations. This should remove almost all routine Gemini text-review
calls without reducing high-severity recall.

Do not fine-tune or deploy a dedicated cloud model yet. First run the cascade in
shadow/observability mode on real traffic and adjudicate its extra false
positives. Collect several hundred reviewed examples before considering LoRA.
Qwen3 14B is not immediately required; test it only if the false-positive rate
causes unacceptable reviewer workload.

Raw local results are in `_local_review_qwen3_8b_full.json`.

## Update 2026-09-27: efficient local review

Re-run on an RTX 3060 (12 GB) through Ollama 0.34.4, same 114 rows, no Gemini
calls: rows the cascade escalates are scored with the saved Gemini answer, so
the cascade numbers are what would ship. The original run above counted
`REVIEW_REQUIRED` as a catch, which rewards hedging; the table therefore also
shows the trivial "flag everything" policy a reviewer has to beat.

| 114 rows | F1 | Precision | Recall | High-sev misses | Gemini calls | Median local latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Gemini only (saved) | 85.2% | 81.5% | 89.2% | 5 | 100% | – |
| Flag everything | 78.7% | 64.9% | 100% | 0 | 0% | – |
| qwen3:8b, compact output, alone | 81.0% | 76.2% | 86.5% | 6 | 0% | 4.7 s |
| qwen3:4b, compact output, alone (run 1) | 85.5% | 80.0% | 91.9% | 4 | 0% | 3.5 s |
| qwen3:4b, compact output, alone (run 2) | 80.3% | 80.8% | 79.7% | 12 | 0% | 3.7 s |
| **qwen3:4b cascade, shipped gates (run 2)** | **84.7%** | 77.5% | **93.2%** | **4** | **36%** | 3.7 s |

High-severity misses in the last two rows use run 2's cohort (64 rows); the
earlier rows use each run's own cohort.

What changed and why:

- **Compact output (`LocalReviewV1`).** The model writes a short rationale and
  the enums; summary and disclaimer are filled in by code. Output fell from
  ~170 to ~95–130 tokens and median latency from ~20 s to 3.5–4.7 s.
- **Citations constrained in the decoding grammar.** `cited_signal_ids` is an
  enum of the request's real signal ids, so the model can no longer copy
  violation UUIDs (which forced a fallback and cost ~25 tokens each).
- **`qwen3:4b` is the default.** It matched or beat 8B on every run and decodes
  at ~71–77 tokens/s versus ~50.
- **Cascade gates are objective only.** Invalid output, missing verdict, and a
  local `COMPLIANT` (all local misses were clearances that echoed a matcher
  which also missed the issue) go to Gemini. `agreement_with_deterministic` is
  no longer a gate: 4B reported "diverges" on 81% of rows, which sent 97% of
  traffic to Gemini.
- **`num_ctx` 32k → 8k.** Review prompts measure ~5k tokens.

Caveats:

- Two identical 4B runs differed by 5 F1 points. Single runs on 114 rows are
  not reliable enough to separate models within a few points; compare the
  cascade, which is steadier, and repeat runs before deciding.
- The gates were chosen on these same rows. `--split test` gives a stable 32-row
  subset; on it the shipped cascade scored 83.7% F1 / 90% recall versus
  Gemini's 85.7% / 90%, with 37.5% Gemini calls.
- Thinking (`OLLAMA_REVIEW_THINK=1`) was stopped after 18 rows: ~5× output
  tokens (~13 s median). Not evaluated.
- 4B still answers `REVIEW_REQUIRED` on about half of assets. That is the
  remaining cost (reviewer workload), and the next thing to reduce.
