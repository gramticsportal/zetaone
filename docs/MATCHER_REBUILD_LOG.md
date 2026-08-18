# Matcher rebuild — state and next steps

Working log, paused 2026-08-12. Everything below is in the working tree, uncommitted.

## Why this happened

The eval set had 2,214 non-compliant rows against 190 compliant ones, and the compliant
rows were generic ("A daily multivitamin to help support your overall wellness"). Generic
negatives share no vocabulary with the positives, so clearing them proves nothing about
the matcher. We built minimal pairs to fix that, and the pairs immediately showed the
matcher was performing below chance.

## What was done

### 1. Compliant minimal pairs

`ontology/tools/generate_compliant_pairs.py` → `ontology/examples/eval_compliant_pairs.yaml`

1,405 pairs, capped at 2 per precedent. Each is the closest lawful version of a real
deceptive ad. The instruction that matters is the one telling Gemini to *keep the risky
wording* wherever a lawful use exists, and only restructure when nothing lawful survives —
85% retain the original trigger. Pairs built by deleting the trigger word would have been
worthless, since they would test only whether the matcher can spot a missing word.

Eval balance went from 2,214/190 to 2,214/1,595. `load_eval.py` now loads
`eval_compliant_pairs.yaml` together with `eval_harvested.yaml` under
`ZATAONE_EVAL_INCLUDE_HARVESTED=1`; loading the harvested positives without the pairs
restores the imbalance they exist to fix.

### 2. Diagnosis

Measured against the pairs, the original matcher scored 42.0% precision where chance is
50%. Causes, in order of size:

- `forbidden_terms` were mined from *policy prose*, so they were the vocabulary of the
  rules rather than of violations. `health.disease_cure_treatment_claims` forbade
  "regardless" and "legality" because its source sentence read "regardless of legality".
  On lawful copy the top triggers were `support` (234), `product` (173), `health` (109).
- Phrase matching used substring containment, so the pack term `elect` flagged "in select
  areas" and "ELECTROLYTES: 2½X THE LEADING SPORTS DRINK" as **paid political advertising**.
- Several packs forbade the disclosure the law *requires*: `paid for by` (FECA), `results
  may vary` (0 violations, 67 lawful ads), and a regex matching "not intended to diagnose,
  treat, cure, or prevent any disease".

### 3. Discriminative re-mining

`ontology/tools/mine_discriminative_triggers.py`

Scores every trigger by log-odds with an informative Dirichlet prior, non-compliant against
compliant. Purged 117 triggers; kept 143; left 962 untested (no eval data — most alcohol,
drugs and political packs), on the principle that an untested trigger is not a disproven one.

The bar is `z >= 0`, not a significance level. A trigger firing on both sides of a pair is
fine in a gated design — the trigger supplies recall, the gate supplies precision. Only
triggers firing *more* on lawful copy must go.

**The mining half found almost nothing.** Beyond `free` and `proven`, no n-gram separates
the classes, because the pairs share vocabulary by construction. This is the central
finding: no bag-of-words feature can do this job. It is what justifies the gate.

### 4. Qualifier gate

`ontology/patterns/qualifiers.yaml`, consumed by `pack_loader.py` and `lexical.py`

20 qualifier classes (substantiation, basis_of_comparison, typicality, conditional_scope,
material_connection, risk_disclosure, hedged_claim, …) plus a per-pack mapping. A pack
listed in `pack_requirements` clears its hit when a qualifier matches within
`QUALIFIER_WINDOW` (240 chars) of the trigger. 34 packs are gated; 18 are absolute, because
no disclaimer makes "cures cancer" or a counterfeit-goods ad lawful.

`LexicalHit.licensed_by` records which class cleared a hit, so an audit trail can show why
something was *not* a violation. `match_lexical(..., drop_licensed=False)` returns cleared
hits for analysis.

**The gate works.** On the violation side it false-cleared 2 hits out of 1,405.

### 5. Claim-strength triggers

The purge cut recall, and inspecting the misses showed why: the packs had no triggers for
the most common violation shape. Comparative superiority claims dominated — "customer
loyalty 4x higher than Xfinity", "up to 12% more hard water minerals than plain salt
pellets", "more powerful than any other glass cleaner". Added to `misleading.yaml`
(comparative, superlative, ranking, up-to, efficacy verb, certainty, speed, absolute scope)
and `health.yaml` (structure/function, plus non-disease context terms so the pack's context
gate stops discarding "Improves your energy levels" before matching).

Also fixed word boundaries via lookarounds rather than `\b`, since triggers include `#ad`
and `100%` where `\b` never matches.

### 6. Honest measurement

`ontology/tools/eval_matcher_pairs.py` — dev/test split by hash of example id, because the
thresholds are tuned against these same pairs. Tune on dev, quote test.

Held-out test split, 720 pairs:

| | recall | precision | F1 | fires only on lawful copy |
|---|---|---|---|---|
| baseline | 28.9% | 42.0% | 0.342 | 16.2% |
| now | 33.6% | 57.6% | 0.425 | 6.7% |

Latency ~1.3 ms/ad (was 147 µs). Slower because of the added regexes, still ~750 ads/sec
per core, and speed was never the constraint.

A stricter threshold for single-token triggers looked obviously right but moved F1 the
wrong way at every setting above zero on dev, so the knob was removed rather than kept at a
tuned constant. That sweep is recorded in the tool's comments.

`ZATAONE_EVAL_INCLUDE_HARVESTED=1 python3.11 ontology/validate.py` passes; 17 hybrid/pack
tests pass.

## Where it stands

59.3% of violations still match no trigger at all. That is now the entire recall problem —
the gate is not the bottleneck, trigger coverage is. Sampling those misses shows two kinds:

- Reachable with better patterns or a semantic channel: "Helps patients with diabetes",
  "Improves your energy levels", "Unsurpassed HD picture quality", "Scientifically
  Formulated to Maximize Sports Performance".
- Not reachable and arguably not valid eval rows: "curved and stretchy fit", "has your back
  every day", "gel without the light". These are fragments the harvester pulled out of
  enforcement documents; they are not self-evidently deceptive in isolation. Some of the
  remaining gap is data quality, not engine quality.

## Next steps

1. **Feasibility check for the embedding channel, before building it.** A TF-IDF
   nearest-neighbour proxy over dev-split violations, evaluated on the test pairs the
   lexical layer misses entirely, gives a cheap lower bound on what embeddings would
   recover. This was mid-run when work stopped. If it separates violation from lawful twin
   at all, real embeddings will do better; if it does not, reconsider before adding a
   dependency. No new packages needed — `sklearn` and `numpy` are installed.

2. **Quantify how much of the 59.3% is harvest noise.** Sample ~100 no-trigger misses and
   label whether each is a genuine standalone claim. This sets the real recall ceiling.
   Without it we will chase recall that is not achievable and may not be desirable.

3. **Then decide on the embedding channel.** If built: exhaustive cosine over the ~2,000
   violation texts (3 MB, no ANN index — approximate search would cost determinism to solve
   a problem this corpus does not have), run only when the lexical layer clears the text, so
   it costs nothing on flagged traffic. Keep it **advisory**: it may route to human review,
   never block. Then every blocking decision stays pure string-and-integer logic with a
   cited clause and a span, and the determinism claim survives float drift across hardware.

4. **Corpus gaps found along the way.** No clauses exist for FTC Green Guides
   (biodegradable, eco-friendly, recyclable) or Made in USA, and violations of both appear
   in the harvested data — "renders plastic products biodegradable", "Made in the USA since
   1947". Triggers were deliberately not written for these, since there is no clause to
   cite. Adding the clauses is a corpus task, not a matcher task.

5. **Re-mine once categories have data.** Mining was skipped for alcohol, discrimination,
   drugs, gambling, ip_trademark, political and privacy — all have fewer than 40 examples
   per side. Their 962 untested triggers are carried on trust.

## Files

New:
- `ontology/tools/generate_compliant_pairs.py`
- `ontology/tools/mine_discriminative_triggers.py`
- `ontology/tools/eval_matcher_pairs.py`
- `ontology/patterns/qualifiers.yaml`
- `ontology/examples/eval_compliant_pairs.yaml`

Modified:
- `src/zataone/policy_engine/hybrid/lexical.py` — gate, word boundaries, `licensed_by`
- `src/zataone/policy_engine/hybrid/pack_loader.py` — `load_qualifiers`, `qualifier_classes`
- `ontology/patterns/by_category/*.yaml` — purge (all 11), new triggers (misleading, health)
- `ontology/examples/load_eval.py` — pairs load alongside harvested

Note: `/tmp/packs_pre_purge` and `/tmp/packs_final` were scratch copies during tuning and
will not survive a reboot. The working tree holds the final state; the purge is reproducible
from the pre-purge packs via `mine_discriminative_triggers.py --apply`, but re-running it on
already-purged packs is a no-op, not a double-purge.
