# `ontology/precedents/` — enforcement-precedent layer (Phase 2)

This layer connects the **policy corpus** to **real-world enforcement**, building a
regulatory knowledge graph:

```
Policy  ->  Canonical Rule  ->  Precedent  ->  Evidence  ->  Verdict
```

It is a **sidecar** built on top of the frozen ontology (`schema.yaml` v1.0.0 is
**not** changed). Each precedent references existing corpus `clause_id`s and
`canonical_id`s, so a verdict can be traced back to the exact policy text and the
cross-source canonical rule it implicates.

## What goes here

Official, verifiable enforcement records and policy events:

- Enforcement actions (FTC, SEC, FDA, DOJ/HUD, EEOC, state AGs, platforms, …)
- Official warning letters
- Consent orders / settlements
- Civil penalties and fines
- Suspensions / marketing-denial orders
- Court cases / injunctions
- Policy updates over time (where they set precedent)

## Files

| File | Count | Focus |
|------|-------|-------|
| `precedents.yaml` | 6 | COPPA, Fair Housing, Kardashian, Teami (seed) |
| `ftc.yaml` | 10 | Health/misleading/privacy/deceptive marketing (seed) |
| `sec.yaml` | 4 | Crypto touting, BlockFi, Ripple (seed) |
| `fda.yaml` | 2 | JUUL MDO, COVID fraud warnings (seed) |
| `eeoc_hud.yaml` | 2 | Meta age discrimination, HUD FHA charge (seed) |
| `ftc_expansion.yaml` | 14 | Phase 1 FTC cases (privacy, COPPA, lead-gen, reviews) |
| `sec_expansion.yaml` | 5 | Phase 1 SEC crypto/influencer touting |
| `cfpb.yaml` | 5 | Overdraft, student loans, mortgage ads, debt relief |
| `finra.yaml` | 2 | M1 + Robinhood finfluencer supervision |
| `fec.yaml` | 7 | Disclaimer enforcement, electioneering, reporting |
| `state_ag.yaml` | 3 | NY AG JUUL, DraftKings/FanDuel, sports-betting alert |
| `doj.yaml` | 5 | Counterfeit goods, Operation In Our Sites, Project Copycat |
| `platforms.yaml` | 15 | Meta/Google/TikTok/LinkedIn/Amazon/X policy enforcement |
| `ttb.yaml` | 2 | TTB alcohol energy-claim + clean-beer guidance |
| `fda_expansion.yaml` | 5 | Puff Bar, Curaleaf CBD, delta-8 batch warnings |
| `gambling.yaml` | 5 | NJ DGE self-exclusion and promotion penalties |
| `hud_expansion.yaml` | 1 | HUD Facebook housing charge |
| `README.md` | — | This file |

**Total: 93 verified precedents** (24 seed + 35 Phase 1 + 34 Phase 2). Target: 120–150 over multiple phases.

## Entry shape

Each entry in `precedents[]`:

| field | required | notes |
|-------|----------|-------|
| `precedent_id` | yes | `prec.<org>.<slug>_<year>` |
| `source` | yes | enforcing organization(s) |
| `source_url` | yes | official case / order / press-release URL |
| `date` | yes | ISO date of the action |
| `title` | yes | case title |
| `summary` | yes | short factual summary |
| `why_this_matters` | yes | retrieval / reasoning hook |
| `retrieval_keywords` | yes | list of search terms |
| `confidence` | yes | `verified` \| `unverified` |
| `last_verified_at` | yes | ISO date source was last confirmed |
| `category_ids` | — | ontology categories implicated |
| `violated_clause_ids` | — | corpus clause ids (validated) |
| `canonical_ids` | — | canonical rule ids (validated) |
| `outcome` | yes | `warning_letter` \| `consent_order` \| `settlement` \| `civil_penalty` \| `fine` \| `suspension` \| `court_order` \| `injunction` \| `marketing_denial` \| `refund` \| `no_action` \| `guidance` |
| `monetary_relief` | — | headline figure, as published |
| `status` | — | `final` \| `proposed` \| `on_appeal` \| `rescinded` \| `vacated` |
| `jurisdiction` | — | e.g. `US` |
| `retrieved_at` | — | when the source was first ingested |
| `evidence` | yes | list of `{ quote, source_url, section? }` (verbatim) |

Each precedent should link to **at least one** `violated_clause_id` or
`canonical_id`, and carry **at least one** verbatim `evidence` citation.

## Standards (same as the corpus)

- Official sources only; verbatim quotes; deep links.
- Never invent facts, figures, dates, or links.
- `python ontology/validate.py` must pass (referential integrity on
  `violated_clause_ids`, `canonical_ids`, and `category_ids`).

## Phase 2 coverage snapshot (34 added)

| Vertical | Precedents (live) |
|----------|-------------------|
| Misleading | 55 |
| Financial | 28 |
| Gambling | 11 |
| Health | 18 |
| Political | 10 |
| Drugs / tobacco / cannabis | 9 |
| IP / counterfeit | 7 |
| Minors / COPPA | 11 |
| Privacy | 9 |
| Alcohol | 2 |
| Discrimination | 6 |

Run `python ontology/benchmark/coverage.py` for live stats.

## Roadmap — Phase 3 (not started)

Remaining depth and breadth:

- **International** — EU/UK/CA/AU regulator actions (only after US corpus gaps are filled).
- **State AG depth** — additional gambling, alcohol, and IP actions beyond NY/NJ.
- **Platform transparency** — newer quarterly enforcement metrics (Meta/Google/TikTok reports).
- **FINRA / CFPB** — mortgage-ad repeat offenders, credit-repair cloud cases, additional finfluencer discipline.
- **Political** — state election-ad enforcement; synthetic-media disclosure cases at scale.
- **Gambling** — additional state DGE/AG actions (PA, MI, IL regulators).

Add new files by agency (`ttb.yaml`, `fec.yaml`, …) or domain — never invent facts;
always link to corpus clauses/canonicals.
