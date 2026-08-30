# Prompt — ZetaOne one-page infographic

Paste everything below the line into another LLM. It is self-contained: all figures,
formulas and layout instructions are included, so the model needs no other context.

Two accuracy notes before you send it, so the output does not misstate the system:

- The classifier is **numpy-only**. scipy and scikit-learn are installed in the
  environment but were deliberately not used — the optimiser is hand-written full-batch
  gradient descent so that training is bit-for-bit reproducible and the artifact carries
  no framework dependency. The prompt says this explicitly; keep it that way.
- The `0.932` north-star figure is **in-sample** and must keep its asterisk and footnote.
  Dropping it would turn an honest report into a misleading one.

---

Produce a **single-page A4 portrait infographic** (210×297mm) summarising the technical
results below. Deliver it as **LaTeX** using TikZ for the diagram, compilable with
`pdflatex` — no external images, no downloads, no shell-escape. If you cannot emit LaTeX,
emit a single self-contained HTML file with inline SVG and MathJax instead.

## Subject

**ZetaOne** — an advertising-compliance engine with two tiers: a deterministic policy
engine, and a small learned model that acts only as a sensor. Tagline: *deterministic
policy engine + learned sensor*.

Corpus metadata line for the header: `Ad Corpus v0.12 · 172 clauses · 137 rules ·
54 canonical rules · 28 sources · 1,588 enforcement precedents · every figure is the
held-out test split`.

## Required sections, in this order

### 1. Architecture diagram (full width, top)

Left-to-right flow, with a second tier branching off:

```
Asset ──▶ Sensors ──▶ Document
(text·image·A/V)  (VLM·OCR·ASR)  (normalised + spans)
                                    │
                                    ▼
  TIER 1 — DETERMINISTIC  (blue box containing a 5-step chain)
  Fold ─▶ Packs ─▶ Gate ─▶ Predicates ─▶ Negation
  (homoglyph  (54 packs,  (23 licence   (APR, age    (6 packs)
   ·leet)      1,298 rules) classes)     thresholds)
                                    │
                                    ▼
                              Violations ──▶ Verdict
                              (+ evidence)   (risk · audit)

  TIER 2 — LEARNED SENSOR  (amber box, upper right)
  "runs only where Tier 1 is silent — 50% of traffic;
   recommends HUMAN REVIEW, never a violation"
                                    │
                                    ▼
                              Review queue (human decides)
```

Caption under the diagram, italic: *Models are sensors: they extract signals and never
decide a verdict.*

Colour code and keep it consistent throughout: Tier 1 / deterministic = blue `#1f5fa8`,
Tier 2 / model = amber `#b8690f`, cascade = green `#1d7a4f`, caveats = red `#a32b2b`.

### 2. Three configuration panels (equal thirds)

**Panel A — DETERMINISTIC** (blue). Subtitle: *Guarded licensing, not classification.*

The core formula:

    V(d,p) = T(d,p) ∧ ¬E(d) ∧ C(d) ∧ ¬∃c ∈ Q(p) : L_c(W(d))

with the note *monotone in triggers, antitone in licences*. Then:
825 terms · 287 phrases · 186 regex; 23 licence classes · 146 patterns; window W = 240
characters around the trigger; 36 packs licensable · 18 absolute.

Risk score:  `R = min(100, Σ_i π(s_i)·μ(c_i))`  where π ∈ {100, 50, 20, 5} by severity and
μ ∈ {1.0, 0.7, 0.3} by confidence.

Headline: **P 0.826 · R 0.593 · F1 0.690**, specificity 0.704, ~5 ms/row.

**Panel B — LANGUAGE MODEL** (amber). Subtitle: *Linear, inspectable, reproducible.*

    x = [ n̂(d) ; φ(d) ] ∈ ℝ^20010
    p = σ(wᵀx + b)

where n̂ is L2-normalised word 1–2-grams plus character 4-grams, and φ is 10 structural
flags. Objective:

    J = −Σ_i α_i [ y_i log p_i + (1−y_i) log(1−p_i) ] + (λ/2)‖w‖²

Optimiser: w⁽⁰⁾ = 0, full batch, η_t = η/(1 + t/100), 400 iterations. Note: *convex ⇒
path-independent ⇒ bit-identical weights*. Artifact: 242 KB `.npz`, **numpy only, no
torch, no scipy, runs offline**.

Headline: **P 0.828 · R 0.869 · F1 0.848**, specificity 0.571, dev AUC 0.837.

**Panel C — BOTH (CASCADE)** (green). Subtitle: *Tier 2 asked only where Tier 1 is silent.*

    d ∨ (s ∧ ¬d)  ≡  d ∨ s

with the note *the same predicate — a cascade earns its name on cost, not on the decision*.
Expected latency:

    E[T] = Σ_i ( Π_{j<i} e_j ) t_i        (escalation rate e dominates, not tier speed)

Where Tier 1 is silent (339 of 684 rows): recovers **86%** of the violations it missed,
false-alarms on **38%** of the clean copy. Also show: confirmed (d ∧ s) → P 0.883,
specificity 0.837.

Headline: **P 0.799 · R 0.942 · F2 0.909**, specificity 0.438, recall +58%.

### 3. Mathematics block — six cells in a 3×2 grid

This section matters most; render every formula properly, not as plain text.

1. **Why this is not a classifier.** `I(words ; y) ≈ 0`. 85% of compliant minimal pairs
   carry the same trigger as the violation they pair with, by construction. Vocabulary
   cannot separate them; the licence gate can. The information is in the structure, not
   the words.
2. **Calibration is empirical Bayes.** `ĉ = (k + mπ)/(n + m)`, m = 8. Beta-Binomial
   posterior mean. Every regex shipped at 0.88; measured, they range 0.19 to 0.64.
3. **Variance is clustered** (red). `SE = √(p(1−p)/G)`, G = 128. Rows inside one
   enforcement case are not independent — they restate one claim. Effective n is 128
   cases, not 347 rows. Therefore **P = 0.824 ± 0.066, not ± 0.040** — a design effect of
   1.65×. Compare engines with a cluster bootstrap over cases, or manufacture significance
   from correlated rows.
4. **The loss is asymmetric.** `L = c_FN·FN + c_FP·FP` with `c_FN > c_FP`. A missed
   violation costs more than a flagged ad, so report `F₂ = 5PR/(4P+R)` rather than F₁.
5. **Evidence is double-counted** (red). Currently `R = Σ_i π_i μ_i`, which assumes
   independence. "cure for cancer" — three words, one span — fires 8 packs and scores 100
   out of 100. That measures how densely the pack library covers a phrase, not how bad the
   ad is. Fix (green): `P = 1 − Π_i (1 − p_i)` over distinct spans — bounded,
   order-independent, immune to adding redundant packs.
6. **The split unit is the case.** 1,589 rows ← 827 cases ⇒ split by case: 578 / 121 / 128
   groups. 13 north-star cases are locked to test, so a harvested sibling can never leak
   into training.

### 4. Two bottom panels, side by side

**Left — WHAT THE NUMBERS DO NOT SAY** (red-tinted). Heading: *The model did not learn the
rule.* Table of recall by source on the held-out split:

| source | deterministic | model |
|---|---|---|
| harvested — enforcement wording | 0.490 | **0.908** |
| precedents — expert, north star | 0.932* | **0.864** |
| seed — expert, third register | 0.732 | **0.772** |
| compliant pairs — *specificity* | — | **0.564** |

Footnote: `* in-sample: the miner tokenised those rows straight into pack terms.`

Closing text: *0.564 on minimal pairs is a coin flip. It learned that enforcement-quoted
copy reads differently from a rewrite — not the rule. Its own `explain()` agrees: the
top-weighted features on escalated copy are "c: the" and "w:the".*

**Right — HELD-OUT RESULTS.** Caption: 684 rows · 128 enforcement cases · test split.

| configuration | P | R | F1 | F2 | spec |
|---|---|---|---|---|---|
| deterministic | 0.826 | 0.593 | 0.690 | 0.628 | 0.704 |
| language model | 0.828 | 0.869 | 0.848 | 0.860 | 0.571 |
| **cascade (d ∨ s)** | **0.799** | **0.942** | **0.865** | **0.909** | **0.438** |
| confirmed (d ∧ s) | 0.883 | 0.520 | 0.654 | 0.566 | 0.837 |

Closing text: *Recall 0.593→0.942 and F₂ 0.628→0.909 are real. Specificity 0.704→0.438 is
the price, and in a review queue that price is reviewer time — so the learned tier ships
behind a flag, off by default.*

### 5. Footer

`Training is deterministic — same split, same weights, bit for bit. Mining reads train
only; test is reporting-only.` Date: 2026-08-23.

## Design constraints

- Everything must fit on **one page**. Prefer dropping decoration over shrinking text
  below 5.5pt. Nothing may overlap or overflow its container — check the compiled output.
- Restrained, technical, print-like. White background, thin rules, generous whitespace.
  No stock icons, no gradients, no drop shadows, no emoji.
- Numbers are the hero: set the three headline metric lines noticeably larger and in the
  panel's accent colour.
- **Do not round, average or otherwise alter any figure**, and do not drop the asterisk or
  its footnote. The caveat panel is as important as the results panel; a version that
  keeps only the good numbers is a failed version.
