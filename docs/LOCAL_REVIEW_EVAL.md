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
