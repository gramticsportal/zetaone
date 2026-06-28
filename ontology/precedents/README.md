# `ontology/precedents/` — enforcement-precedent layer (Phase 3 complete)

This layer connects the **policy corpus** to **real-world enforcement**, building a
regulatory knowledge graph:

```
Policy  ->  Canonical Rule  ->  Precedent  ->  Evidence  ->  Verdict
```

It is a **sidecar** built on top of the frozen ontology (`schema.yaml` v1.0.0 is
**not** changed). Each precedent references existing corpus `clause_id`s and
`canonical_id`s, so a verdict can be traced back to the exact policy text and the
cross-source canonical rule it implicates.

## Status: precedent layer complete (128 verified precedents)

Target of 120–150 high-quality US precedents reached. **Do not expand internationally
(EU/UK/CA/AU) or add weak duplicates.** Next project focus: large evaluation dataset,
benchmarking, and pilot customers.

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
| `ftc_phase3.yaml` | 7 | Phase 3 FTC (H&R Block, Instacart, Opendoor, fake reviews rule, …) |
| `sec_expansion.yaml` | 5 | Phase 1 SEC crypto/influencer touting |
| `sec_phase3.yaml` | 5 | Phase 3 SEC (Terraform, Kraken staking, NFT offerings) |
| `cfpb.yaml` | 10 | Overdraft, student loans, mortgage ads, fintech, Apple Card |
| `finra.yaml` | 5 | M1, Robinhood, TradeZero, Moomoo, Webull finfluencer discipline |
| `fec.yaml` | 9 | Disclaimer enforcement, electioneering, IE reporting |
| `state_ag.yaml` | 8 | NY/CA AG healthcare, endorsements, fake reviews, lead-gen |
| `doj.yaml` | 8 | Counterfeit goods, IP seizures, Apple warranty fraud |
| `platforms.yaml` | 19 | Meta/Google/TikTok/LinkedIn/Amazon/X policy enforcement |
| `ttb.yaml` | 3 | TTB alcohol trade-practice and labeling enforcement |
| `fda_expansion.yaml` | 5 | Puff Bar, Curaleaf CBD, delta-8 batch warnings |
| `gambling.yaml` | 5 | NJ DGE self-exclusion and promotion penalties |
| `hud_expansion.yaml` | 1 | HUD Facebook housing charge |
| `README.md` | — | This file |

**Total: 128 verified precedents** (24 seed + 35 Phase 1 + 34 Phase 2 + 35 Phase 3).

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

## Phase 3 coverage snapshot (35 added)

| Vertical | Precedents (live) |
|----------|-------------------|
| Misleading | 86 |
| Financial | 46 |
| Health | 20 |
| Political | 15 |
| Gambling | 12 |
| Drugs / tobacco / cannabis | 9 |
| IP / counterfeit | 10 |
| Minors / COPPA | 11 |
| Privacy | 10 |
| Alcohol | 3 |
| Discrimination | 7 |

Run `python ontology/benchmark/coverage.py` for live stats.

## Remaining meaningful gaps (post Phase 3)

- **International regulators** — EU DSA, UK ASA, CA Competition Bureau, AU TGA (deferred).
- **State AG depth** — PA/MI/IL gambling, additional alcohol/IP beyond NY/CA/NJ.
- **Platform quarterly metrics** — newer Meta/Google/TikTok enforcement dashboards.
- **Synthetic-media at scale** — few litigated cases beyond platform policy rules.
- **Cannabis/tobacco** — FDA/TTB thick; state cannabis ad enforcement thin.
- **LinkedIn / X / Amazon** — fewer enforcement-metric precedents vs policy pages.

Add new files by agency (`ttb.yaml`, `fec.yaml`, …) or domain — never invent facts;
always link to corpus clauses/canonicals.
