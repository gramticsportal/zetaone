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
| after gate + triggers | 33.6% | 57.6% | 0.425 | 6.7% |
| after bug fixes (current) | 39.9% | 60.3% | 0.480 | — |

Latency ~400 µs/ad (was 147 µs baseline), ~2,500 ads/sec per core. Speed was never the
constraint.

A stricter threshold for single-token triggers looked obviously right but moved F1 the
wrong way at every setting above zero on dev, so the knob was removed rather than kept at a
tuned constant. That sweep is recorded in the tool's comments.

`ZATAONE_EVAL_INCLUDE_HARVESTED=1 python3.11 ontology/validate.py` passes; 17 hybrid/pack
tests pass.

### 7. Session 2 — audit, and three bugs it exposed

`ontology/tools/audit_missed_violations.py` → `ontology/examples/missed_violations_audit.csv`

Sampled 200 of the no-trigger misses and had them labelled. **66% are genuinely assessable
claims; 34% are extraction noise** — 18.5% fragments ("keep up with all of this", "control
who can see"), 15.5% not claims at all (product names, headings). So roughly a third of the
apparent recall gap is harvester debris, and the realistic ceiling is nearer 66% of the
missing rows than 100%. Labels were spot-checked and are broadly sound, though the model
slightly over-calls `not_a_claim` on taglines.

Spot-checking also caught three real bugs, all found by asking why rows the audit called
assessable had not fired:

- `\b(?:no\.?\s*1|#\s*1|...)` could never match "#1 Horse Book Club": `#` is not a word
  character, so `\b#` fails after a space. Now uses a lookbehind. Same class of bug as the
  `elect`/"select" one, in a regex rather than a term.
- `\s+` did not span the ellipses that enforcement exhibits use for elided text, so
  "faster . . . antiplatelet response than enteric coated aspirin" was missed. The gap now
  admits punctuation.
- **The costly one.** `basis_of_comparison` contained `\bthan\s+[A-Z][\w-]+`, intended to
  treat a named rival as a stated basis. Every pattern in `qualifiers.yaml` compiles with
  `re.IGNORECASE`, so `[A-Z]` matched lowercase too and "than enteric coated aspirin"
  counted as a basis — licensing most comparatives and driving gate false-clears from 2 to
  51. Removed rather than made case-sensitive: naming the rival is not a basis for a
  *quantified* claim, which still needs the evidence.

Fixing those took test-split recall 33.6% → 39.9%, precision 57.6% → 60.3%, F1 0.425 →
0.480, and gate false-clears 51 → 19. Latency also fell to ~400 µs/ad.

### 8. Embedding channel feasibility (TF-IDF lower bound)

Char n-gram TF-IDF kNN, index built only from dev-split violations, evaluated on the test
pairs the lexical layer misses entirely (427 rows). Result is **weak**: at a usable
false-positive rate (3.3% of lawful twins, sim >= 0.60) it recovers only 8% of missed
violations. But violations rank strictly closer to known violations than their own lawful
twin 71.7% of the time, against 50% for no signal — so there is real signal in the ranking,
just not at a usable absolute threshold.

Two caveats before drawing conclusions: this is surface-level TF-IDF and therefore a lower
bound on what real embeddings would do, and it was measured over misses that are ~34%
extraction noise, which depresses it further. **Re-run this over only the assessable rows
before deciding.**

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

Steps 1 and 2 from the first session are done (sections 7 and 8 above). Resume here:

1. **Drop or quarantine the 34% extraction noise in `eval_harvested.yaml`.** The audit
   labelled a 200-row sample; extend it to all 1,160 no-trigger misses, then either remove
   the fragments and non-claims or mark them so `eval_matcher_pairs.py` can exclude them.
   Measured recall will rise without any matcher change, and every downstream number
   becomes trustworthy. Do this first — it is cheap and it conditions everything else.

2. **Re-run the TF-IDF feasibility check over assessable rows only.** The 8% recovery
   figure was computed over misses that are a third noise, so it understates the ceiling by
   an unknown margin. If it stays weak on clean rows, real embeddings are unlikely to be
   worth the dependency and the effort belongs in triggers instead.

3. **Keep hunting trigger bugs the way section 7 did.** Three real bugs came out of asking
   why individual assessable misses did not fire, and that had a bigger payoff than any
   threshold tuning in this project so far (F1 +0.055 in one pass). The audit CSV is a ready
   queue of such cases.

4. **Then decide on the embedding channel.** If built: exhaustive cosine over the ~2,000
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
