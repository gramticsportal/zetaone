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

| File | Purpose |
|------|---------|
| `precedents.yaml` | Precedent entries (referential to the corpus) |
| `README.md` | This file |

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
| `category_ids` | — | ontology categories implicated |
| `violated_clause_ids` | — | corpus clause ids (validated) |
| `canonical_ids` | — | canonical rule ids (validated) |
| `outcome` | yes | `warning_letter` \| `consent_order` \| `settlement` \| `civil_penalty` \| `fine` \| `suspension` \| `court_order` \| `injunction` \| `marketing_denial` \| `refund` \| `no_action` \| `guidance` |
| `monetary_relief` | — | headline figure, as published |
| `status` | — | `final` \| `proposed` \| `on_appeal` \| `rescinded` \| `vacated` |
| `jurisdiction` | — | e.g. `US` |
| `retrieved_at` | — | when the source was last read |
| `evidence` | yes | list of `{ quote, source_url, section? }` (verbatim) |

Each precedent should link to **at least one** `violated_clause_id` or
`canonical_id`, and carry **at least one** verbatim `evidence` citation.

## Standards (same as the corpus)

- Official sources only; verbatim quotes; deep links.
- Never invent facts, figures, dates, or links.
- `python ontology/validate.py` must pass (referential integrity on
  `violated_clause_ids`, `canonical_ids`, and `category_ids`).

## Seed set (Precedents v0.1)

| `precedent_id` | Vertical | Outcome |
|----------------|----------|---------|
| `prec.ftc.google_youtube_coppa_2019` | Minors / Privacy | $170M settlement |
| `prec.ftc.musically_tiktok_coppa_2019` | Minors / Privacy | $5.7M settlement |
| `prec.ftc.epic_games_coppa_2022` | Minors / Privacy | $275M + $245M |
| `prec.doj_hud.meta_fair_housing_2022` | Discrimination | $115,054 + VRS |
| `prec.sec.kardashian_ethereummax_2022` | Financial / Misleading | $1.26M + 3-yr ban |
| `prec.ftc.teami_health_influencers_2020` | Health / Misleading | $15.2M judgment |

## Roadmap (expand incrementally, like the corpus)

Seed coverage spans Minors/Privacy, Discrimination, Financial, and Health. Still
to add (verify official sources before entry):

- **Alcohol / Tobacco / Nicotine** — FDA/FTC marketing actions and warning letters.
- **Gambling** — state-AG / regulator actions (US gambling is state-regulated).
- **IP / Counterfeit** — Lanham Act judgments and platform/brand enforcement.
- **Political** — FEC matters and disclaimer-related actions.
- Non-US jurisdictions (EU/UK) and additional platforms (X, Amazon Ads).
