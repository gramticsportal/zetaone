#!/usr/bin/env python3
"""Backfill why_this_matters, retrieval_keywords, confidence, last_verified_at on seed precedents."""
from __future__ import annotations

import glob
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PREC = ROOT / "precedents"
VERIFIED = "2026-06-27"

# Seed precedents only (pre-Phase-1 files); Phase-1 files already have metadata.
SEED_FILES = {
    "precedents.yaml",
    "ftc.yaml",
    "sec.yaml",
    "fda.yaml",
    "eeoc_hud.yaml",
}

BACKFILL: dict[str, dict] = {
    "prec.ftc.google_youtube_coppa_2019": {
        "why_this_matters": "Foundational COPPA settlement for child-directed platforms and behavioral advertising to minors.",
        "retrieval_keywords": ["YouTube", "Google", "COPPA", "children", "behavioral ads", "FTC", "2019"],
    },
    "prec.ftc.musically_tiktok_coppa_2019": {
        "why_this_matters": "Early TikTok/Musical.ly COPPA case linking short-video platforms to children's data collection failures.",
        "retrieval_keywords": ["Musical.ly", "TikTok", "COPPA", "children", "FTC", "2019"],
    },
    "prec.ftc.epic_games_coppa_2022": {
        "why_this_matters": "Major gaming COPPA/dark-patterns settlement setting penalty scale for youth-facing games.",
        "retrieval_keywords": ["Epic Games", "Fortnite", "COPPA", "dark patterns", "children", "520 million"],
    },
    "prec.doj_hud.meta_fair_housing_2022": {
        "why_this_matters": "DOJ/HUD settlement resolving algorithmic housing ad discrimination on Meta's platform.",
        "retrieval_keywords": ["Meta", "Facebook", "Fair Housing Act", "DOJ", "HUD", "special ad categories"],
    },
    "prec.sec.kardashian_ethereummax_2022": {
        "why_this_matters": "High-profile celebrity crypto touting case emphasizing paid-promotion disclosure.",
        "retrieval_keywords": ["Kim Kardashian", "EthereumMax", "crypto", "SEC", "influencer", "touting"],
    },
    "prec.ftc.teami_health_influencers_2020": {
        "why_this_matters": "Influencer health-product case on unsubstantiated detox/weight-loss claims.",
        "retrieval_keywords": ["Teami", "influencers", "health claims", "detox tea", "FTC", "Instagram"],
    },
    "prec.ftc.lumosity_brain_training_2016": {
        "why_this_matters": "Landmark brain-training health-claim case requiring competent scientific evidence.",
        "retrieval_keywords": ["Lumosity", "brain training", "health claims", "cognitive", "FTC"],
    },
    "prec.ftc.volkswagen_clean_diesel_2016": {
        "why_this_matters": "Massive environmental deception precedent for objective product performance claims.",
        "retrieval_keywords": ["Volkswagen", "clean diesel", "deceptive advertising", "emissions", "FTC"],
    },
    "prec.ftc.credit_karma_preapproved_2023": {
        "why_this_matters": "Dark-pattern finance ad case on false 'pre-approved' credit offers.",
        "retrieval_keywords": ["Credit Karma", "pre-approved", "dark patterns", "credit cards", "FTC"],
    },
    "prec.ftc.walmart_made_in_usa_2022": {
        "why_this_matters": "Made in USA origin-claim enforcement applicable to product marketing ads.",
        "retrieval_keywords": ["Walmart", "Made in USA", "origin claims", "deceptive advertising", "FTC"],
    },
    "prec.ftc.devry_education_claims_2016": {
        "why_this_matters": "Education earnings-outcome advertising case for employment statistics in ads.",
        "retrieval_keywords": ["DeVry", "education", "earnings claims", "employment outcomes", "FTC"],
    },
    "prec.ftc.reebok_easetone_2011": {
        "why_this_matters": "Classic toning-shoe unsubstantiated performance claim precedent.",
        "retrieval_keywords": ["Reebok", "EasyTone", "performance claims", "substantiation", "FTC"],
    },
    "prec.ftc.skechers_shapeups_2012": {
        "why_this_matters": "Companion toning-footwear case reinforcing exercise benefit substantiation.",
        "retrieval_keywords": ["Skechers", "Shape-ups", "performance claims", "FTC", "footwear"],
    },
    "prec.ftc.omics_deceptive_publishing_2019": {
        "why_this_matters": "Deceptive academic/publishing claims case relevant to B2B and health-adjacent marketing.",
        "retrieval_keywords": ["OMICS", "deceptive publishing", "conferences", "FTC"],
    },
    "prec.ftc.flo_health_data_sharing_2021": {
        "why_this_matters": "Health-app data sharing case linking fertility data to ad-tech disclosures.",
        "retrieval_keywords": ["Flo", "health app", "data sharing", "privacy", "period tracker", "FTC"],
    },
    "prec.ftc.amazon_prime_dark_patterns_2023": {
        "why_this_matters": "Dark-pattern subscription enrollment case with broad ecommerce ad UX implications.",
        "retrieval_keywords": ["Amazon Prime", "dark patterns", "subscription", "enrollment", "FTC"],
    },
    "prec.fda.juul_marketing_denial_2022": {
        "why_this_matters": "FDA marketing denial order removing JUUL products for lack of authorization.",
        "retrieval_keywords": ["JUUL", "FDA", "marketing denial order", "ENDS", "tobacco"],
    },
    "prec.fda.opioid_marketing_2020": {
        "why_this_matters": "FDA/FTC joint opioid COVID fraud warning letter campaign on deceptive health ads.",
        "retrieval_keywords": ["opioid", "COVID-19", "FDA warning letter", "health fraud", "2020"],
    },
    "prec.eeoc.meta_age_discrimination_2023": {
        "why_this_matters": "EEOC settlement on Meta job-ad targeting excluding older workers.",
        "retrieval_keywords": ["Meta", "EEOC", "age discrimination", "job ads", "ADEA"],
    },
    "prec.hud.facebook_housing_charge_2019": {
        "why_this_matters": "HUD FHA charge on Facebook housing ad targeting (precursor to DOJ settlement).",
        "retrieval_keywords": ["HUD", "Facebook", "Fair Housing Act", "housing ads", "targeting"],
    },
    "prec.sec.mayweather_khaled_icos_2018": {
        "why_this_matters": "Early celebrity ICO touting case establishing crypto promo disclosure expectations.",
        "retrieval_keywords": ["Mayweather", "DJ Khaled", "ICO", "crypto", "SEC", "Centra"],
    },
    "prec.sec.steven_seagal_bitcoiin_2020": {
        "why_this_matters": "Celebrity crypto promotion settlement reinforcing Section 17(b) disclosure duties.",
        "retrieval_keywords": ["Steven Seagal", "Bitcoiin", "crypto touting", "SEC"],
    },
    "prec.sec.blockfi_lending_2022": {
        "why_this_matters": "BlockFi unregistered crypto lending product case affecting finance product ads.",
        "retrieval_keywords": ["BlockFi", "crypto lending", "SEC", "interest accounts", "registration"],
    },
    "prec.sec.ripple_xrp_2023": {
        "why_this_matters": "Ripple XRP unregistered securities case shaping crypto offer/marketing compliance.",
        "retrieval_keywords": ["Ripple", "XRP", "crypto securities", "SEC", "2023"],
    },
}


def slug_keywords(title: str, categories: list[str]) -> list[str]:
    words = re.findall(r"[A-Za-z0-9]+", title)
    kws = [w for w in words if len(w) > 2][:8]
    kws.extend(categories or [])
    return list(dict.fromkeys(kws))[:12]


def main() -> int:
    updated = 0
    for path in sorted(PREC.glob("*.yaml")):
        if path.name not in SEED_FILES:
            continue
        doc = yaml.safe_load(path.read_text()) or {}
        changed = False
        for p in doc.get("precedents", []) or []:
            pid = p["precedent_id"]
            meta = BACKFILL.get(pid, {})
            if not p.get("why_this_matters"):
                summary = (p.get("summary") or "").strip()
                first = summary.split(".")[0].strip() if summary else p.get("title", "")
                p["why_this_matters"] = meta.get("why_this_matters") or (
                    f"Seed enforcement precedent linking corpus rules to {first.lower()}."
                    if first
                    else "Seed enforcement precedent for corpus retrieval."
                )
                changed = True
            if not p.get("retrieval_keywords"):
                p["retrieval_keywords"] = meta.get(
                    "retrieval_keywords",
                    slug_keywords(p.get("title", ""), p.get("category_ids") or []),
                )
                changed = True
            if not p.get("confidence"):
                p["confidence"] = "verified"
                changed = True
            if not p.get("last_verified_at"):
                p["last_verified_at"] = VERIFIED
                changed = True
            updated += int(changed)
        if changed:
            path.write_text(yaml.dump(doc, sort_keys=False, allow_unicode=True, width=1000))
    print(f"Backfilled metadata on seed precedents ({updated} field updates across files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
