#!/usr/bin/env python3
"""Build ontology/examples/eval_precedents.yaml from curated enforcement precedents.

Each row is non_compliant ad copy (verbatim or minimal reconstruction from
official evidence) linked to the precedent's violated_clause_ids.

Run:  python ontology/tools/build_eval_precedents.py
"""
from __future__ import annotations

import glob
import os
import sys

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# precedent_id -> (example_id, content, modality)
# Content is ad/creative text grounded in precedent evidence or summary.
CURATED: dict[str, tuple[str, str, str]] = {
    "prec.sec.kardashian_ethereummax_2022": (
        "prec_ev_kardashian_emax_2022",
        "Are you guys into crypto??? This is not financial advice but sharing what my friends "
        "told me about the EthereumMax token!",
        "text",
    ),
    "prec.sec.paul_pierce_crypto_2023": (
        "prec_ev_paul_pierce_emax_2023",
        "Check out EthereumMax — don't miss this crypto opportunity! (paid promotion, undisclosed)",
        "text",
    ),
    "prec.sec.lindsay_lohan_crypto_2023": (
        "prec_ev_lohan_trx_2023",
        "Excited to share Tronix (TRX) with you — this crypto is going to the moon!",
        "text",
    ),
    "prec.sec.mayweather_khaled_icos_2018": (
        "prec_ev_mayweather_centra_2018",
        "You can call me Floyd Crypto Mayweather — get in on the Centra Tech ICO now!",
        "text",
    ),
    "prec.sec.flyfish_club_nfts_2024": (
        "prec_ev_flyfish_nft_2024",
        "Invest in Flyfish Club NFTs — members can potentially profit from reselling at "
        "appreciated prices on the secondary market.",
        "text",
    ),
    "prec.finra.robinhood_finfluencer_2025": (
        "prec_ev_robinhood_finfluencer_2025",
        "Start trading with Robinhood and watch your money grow — easy passive income from "
        "the stock market! (paid influencer post)",
        "text",
    ),
    "prec.finra.m1_finance_influencers_2024": (
        "prec_ev_m1_influencer_2024",
        "Invest smarter with M1 Finance — build wealth effortlessly with our automated "
        "investing platform! (paid social post)",
        "text",
    ),
    "prec.finra.moomoo_influencers_2024": (
        "prec_ev_moomoo_zero_commission_2024",
        "Trade with zero commission on Moomoo — start investing today!",
        "text",
    ),
    "prec.finra.tradezero_influencers_2024": (
        "prec_ev_tradezero_free_trading_2024",
        "Join TradeZero — the free trading platform that makes you rich from day one!",
        "text",
    ),
    "prec.finra.webull_influencers_2025": (
        "prec_ev_webull_finfluencer_2025",
        "Webull will change your life — guaranteed profits with zero effort! (paid influencer ad)",
        "text",
    ),
    "prec.ftc.teami_health_influencers_2020": (
        "prec_ev_teami_detox_2020",
        "Teami 30 Day Detox Pack helps you lose weight. Our teas fight cancer, clear clogged "
        "arteries, decrease migraines, and treat and prevent flus and colds.",
        "text",
    ),
    "prec.ftc.lumosity_brain_training_2016": (
        "prec_ev_lumosity_brain_2016",
        "Play Lumosity games to stave off memory loss, dementia, and even Alzheimer's disease.",
        "text",
    ),
    "prec.ftc.reebok_easetone_2011": (
        "prec_ev_reebok_easetone_2011",
        "Walking in EasyTone shoes strengthens and tones your leg and buttock muscles more "
        "than regular shoes.",
        "text",
    ),
    "prec.ftc.skechers_shapeups_2012": (
        "prec_ev_skechers_shapeups_2012",
        "Shape-ups help you lose weight and strengthen and tone your buttocks, legs, and "
        "abdominal muscles.",
        "text",
    ),
    "prec.ftc.nextmed_weight_loss_2025": (
        "prec_ev_nextmed_glp1_2025",
        "GLP-1 weight-loss membership — only $138/month! Join thousands who lost 30 lbs.",
        "text",
    ),
    "prec.ftc.evoke_wellness_google_ads_2025": (
        "prec_ev_evoke_clinic_ad_2025",
        "Google search ad: [Your local addiction treatment center] — Call now for immediate "
        "admission (routes to Evoke call center, not the clinic searched).",
        "text",
    ),
    "prec.fda.opioid_marketing_2020": (
        "prec_ev_covid_tea_fraud_2020",
        "Our herbal tea and essential oils can treat or prevent COVID-19 — boost immunity "
        "and stop the virus naturally.",
        "text",
    ),
    "prec.fda.curaleaf_cbd_2019": (
        "prec_ev_curaleaf_cbd_2019",
        "Curaleaf CBD products treat cancer, Alzheimer's, opioid withdrawal, and chronic pain.",
        "text",
    ),
    "prec.nyag.draftkings_fanduel_2016": (
        "prec_ev_draftkings_odds_2016",
        "Deposit $10, get $10 free — everyone wins big on DraftKings daily fantasy!",
        "text",
    ),
    "prec.nyag.sports_betting_superbowl_2022": (
        "prec_ev_sportsbook_riskfree_2022",
        "Place a risk-free bet and claim your $1,000 welcome offer — free money for new players!",
        "text",
    ),
    "prec.ftc.publishers_clearing_house_2023": (
        "prec_ev_pch_sweepstakes_2023",
        "Buy now to complete your sweepstakes entry and increase your chances of winning "
        "$5,000 a week for life from Publishers Clearing House!",
        "text",
    ),
    "prec.ttb.mckenzie_energy_alcohol_2007": (
        "prec_ev_mckenzie_energy_beer_2007",
        "McKenzie River Corporation energy beer — feel the stimulating, energizing boost with "
        "every sip.",
        "text",
    ),
    "prec.ttb.clean_beer_guidance_2022": (
        "prec_ev_clean_beer_2022",
        "Clean beer — clean and healthy. No headaches, no hangovers.",
        "text",
    ),
    "prec.fec.vitter_disclaimer_2009": (
        "prec_ev_vitter_phonebank_2009",
        "[Phone bank call] Vote for David Vitter for U.S. Senate — no 'paid for by' disclaimer.",
        "audio",
    ),
    "prec.fec.ntdo_disclaimer_admonishment_2007": (
        "prec_ev_ntdo_mail_piece_2007",
        "Mass mailing: Elect Dan Seals to Congress — missing required 'paid for by' disclaimer.",
        "text",
    ),
    "prec.ftc.bountiful_review_hijacking_2023": (
        "prec_ev_bountiful_reviews_2023",
        "Amazon listing: 4.5 stars, Amazon's Choice — reviews inherited from unrelated product.",
        "text",
    ),
    "prec.caag.roomster_fake_reviews_2023": (
        "prec_ev_roomster_reviews_2023",
        "Roomster app — 20,000+ verified 5-star reviews. Find trusted roommates instantly!",
        "text",
    ),
    "prec.nyag.cameo_endorsements_2024": (
        "prec_ev_cameo_celebrity_2024",
        "[Cameo video] Celebrity: 'I use this product every day — you should too!' (paid, no #ad)",
        "video",
    ),
    "prec.nyag.google_iheart_pixel_2022": (
        "prec_ev_iheart_pixel_radio_2022",
        "Radio ad script: 'I've been using the Google Pixel 4 and I love it — best phone I've "
        "ever owned.' (personality never used the phone)",
        "audio",
    ),
    "prec.ftc.herbalife_mlm_2016": (
        "prec_ev_herbalife_mlm_2016",
        "Join Herbalife — quit your job and enjoy a lavish lifestyle from distributor earnings!",
        "text",
    ),
    "prec.ftc.devry_education_claims_2016": (
        "prec_ev_devry_jobs_2016",
        "90% of DeVry graduates find jobs in their field within 6 months — earn more than "
        "graduates of other colleges.",
        "text",
    ),
    "prec.ftc.intuit_turbotax_free_2022": (
        "prec_ev_turbotax_free_2022",
        "File your taxes for FREE with TurboTax — free for everyone!",
        "text",
    ),
    "prec.ftc.hrblock_free_filing_2024": (
        "prec_ev_hrblock_free_2024",
        "File your taxes FREE with H&R Block — no cost online filing for all taxpayers.",
        "text",
    ),
    "prec.ftc.credit_karma_preapproved_2023": (
        "prec_ev_credit_karma_preapproved_2023",
        "You're pre-approved for this credit card! Apply now — you're guaranteed approval.",
        "text",
    ),
    "prec.ftc.mediaalpha_insurance_leads_2025": (
        "prec_ev_obamacareplans_2025",
        "ObamacarePlans.com — buy low-cost, comprehensive ACA-compliant health insurance "
        "from the official marketplace.",
        "text",
    ),
    "prec.ftc.assurance_iq_insurance_2025": (
        "prec_ev_assurance_aca_2025",
        "Get comprehensive ACA-compliant health insurance — full Obamacare coverage at "
        "affordable rates.",
        "text",
    ),
    "prec.cfpb.western_benefits_2024": (
        "prec_ev_western_benefits_2024",
        "Official Department of Education partner — consolidate your student loans and get "
        "forgiveness today.",
        "text",
    ),
    "prec.cfpb.rmk_mortgage_ads_2023": (
        "prec_ev_rmk_va_mortgage_2023",
        "VA/FHA-approved lender — get your mortgage approved fast with government backing.",
        "text",
    ),
    "prec.ftc.att_unlimited_data_2019": (
        "prec_ev_att_unlimited_2019",
        "AT&T Unlimited Data plan — truly unlimited high-speed data with no restrictions.",
        "text",
    ),
    "prec.nyag.juul_youth_marketing_2023": (
        "prec_ev_juul_youth_2023",
        "Colorful vape ad featuring young models enjoying fruity, sweet, and minty JUUL flavors.",
        "image",
    ),
    "prec.doj.bugaboo_boutique_counterfeit_2025": (
        "prec_ev_bugaboo_counterfeit_2025",
        "Facebook shop listing: Designer luxury handbag — inspired style, 90% off retail.",
        "text",
    ),
    "prec.caag.cri_genetics_2024": (
        "prec_ev_cri_genetics_reviews_2024",
        "Independent review site: CRI Genetics DNA test — 5 stars, most accurate ancestry "
        "results guaranteed.",
        "text",
    ),
    "prec.ftc.volkswagen_clean_diesel_2016": (
        "prec_ev_vw_clean_diesel_2016",
        "Volkswagen Clean Diesel — environmentally friendly low-emissions driving for a "
        "greener planet.",
        "text",
    ),
    "prec.ftc.opendoor_ibuying_2022": (
        "prec_ev_opendoor_chart_2022",
        "Sell to Opendoor and net thousands more than a traditional home sale — see our chart.",
        "text",
    ),
}


def load_precedents() -> dict[str, dict]:
    by_id: dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "precedents", "*.yaml"))):
        if os.path.basename(path) == "README.md":
            continue
        doc = yaml.safe_load(open(path)) or {}
        for p in doc.get("precedents", []) or []:
            pid = p.get("precedent_id")
            if pid:
                by_id[pid] = p
    return by_id


def main() -> int:
    precedents = load_precedents()
    examples: list[dict] = []
    missing: list[str] = []

    for pid, (eid, content, modality) in CURATED.items():
        p = precedents.get(pid)
        if not p:
            missing.append(pid)
            continue
        vids = p.get("violated_clause_ids") or []
        if not vids:
            print(f"skip {pid}: no violated_clause_ids", file=sys.stderr)
            continue
        examples.append({
            "id": eid,
            "content": content,
            "modality": modality,
            "label": "non_compliant",
            "category_ids": list(p.get("category_ids") or []),
            "violated_clause_ids": list(vids),
            "jurisdiction": p.get("jurisdiction", "US"),
            "labeled_by": "expert",
            "split": "test",
            "note": f"derived_from: {pid}",
        })

    if missing:
        print(f"ERROR: unknown precedent ids: {missing}", file=sys.stderr)
        return 1

    out_path = os.path.join(ROOT, "examples", "eval_precedents.yaml")
    doc = {
        "examples": examples,
    }
    preamble = (
        "# Evaluation examples derived from verified enforcement precedents.\n"
        "# Real-world non_compliant ad copy (verbatim or minimal reconstruction from official\n"
        "# evidence). All rows use split: test. Synthetic seeds remain in eval_seed.yaml.\n"
        "#\n"
        f"# Regenerate: python ontology/tools/build_eval_precedents.py\n"
        f"# Total: {len(examples)} examples (all non_compliant, all test split)\n"
    )
    body = yaml.dump(doc, sort_keys=False, allow_unicode=True, width=1000)
    with open(out_path, "w") as f:
        f.write(preamble + "\n" + body)

    print(f"Wrote {len(examples)} examples to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
