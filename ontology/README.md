# ZataOne Canonical Compliance Ontology

One unified corpus where every **platform** (Meta, Google, TikTok, …) and
**regulator** (FTC, FDA, …) policy maps into the **same underlying ontology**.
This is the foundation for ZataOne's moat: structured corpus + cross-source
mappings + a labeled evaluation dataset with measured precision/recall.

## Files

| File | Purpose |
|------|---------|
| `schema.yaml` | **Canonical schema v0** — entities, fields, allowed values, graph |
| `categories.yaml` | Universal advertising-risk categories (the foundation axis) |
| `corpus/meta_ads_us.yaml` | Meta Ads (US) clauses + rules in the canonical schema |
| `corpus/regulators_us.yaml` | FTC + FDA (US) clauses + rules |
| `mappings.yaml` | Cross-source links: equivalent clauses → one `canonical_id` |
| `examples/eval_seed.yaml` | Labeled evaluation dataset seed |

## Entities

```
category ─< clause >── source
   │           │
   └─< rule >──┘   (rule.canonical_id unifies equivalent rules across sources)
        │
   mapping (clause ↔ clause, same category/canonical_id)
        │
   example >── clause   (eval dataset; label + violated_clause_ids)
```

## Schema highlights (v0)

- **`canonical_id` on rules** — equivalent platform/regulator rules share one universal rule.
- **`priority`** — resolves conflicts when multiple clauses apply (regulator usually outranks platform).
- **`modality`** on clauses/rules — `text · image · video · audio · landing_page`.
- **`status`** (`active · deprecated · superseded`) + **`superseded_by`** — policies change; history is auditable.
- **`last_verified_at`** on sources/clauses — "when did we last confirm this is current?".
- **`confidence`** on mappings (`exact · high · medium`) — not every mapping is perfectly equivalent.

## Scope of this first slice

Deliberately narrow to validate the schema end-to-end before widening:

- **Categories:** `misleading`, `health`
- **Sources:** Meta Ads, FTC, FDA
- **Jurisdiction:** US

## Build order

1. ✅ Canonical schema (this directory).
2. Ingest **Meta Ads** completely into the schema.
3. Ingest **FTC / FDA** and map to the same ontology.
4. Add **Google Ads**, link equivalent clauses.
5. Grow the **evaluation dataset**; measure precision/recall per category.

## Relationship to the engine policies

The legacy rule-engine format lives at
`src/zataone/domains/ad_compliance/policies/*.yaml` (keyword/pattern matching).
This ontology is the **cross-source canonical layer** above it: the engine packs
are one `source`; regulators are another; `mappings.yaml` unifies them. They are
complementary — the ontology does not replace the engine packs.
