#!/usr/bin/env python3
"""Generate Phase 2 precedent YAML sidecars (35 verified entries)."""
from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PREC = ROOT / "precedents"
VERIFIED = "2026-06-27"


def entry(**kwargs) -> dict:
    kwargs.setdefault("confidence", "verified")
    kwargs.setdefault("last_verified_at", VERIFIED)
    kwargs.setdefault("retrieved_at", VERIFIED)
    kwargs.setdefault("status", "final")
    kwargs.setdefault("jurisdiction", "US")
    return kwargs


def dump_file(path: Path, header: str, precedents: list[dict]) -> None:
    lines = [header.rstrip(), "", "precedents:"]
    for p in precedents:
        lines.append(f"  - precedent_id: {p['precedent_id']}")
        for key in (
            "source",
            "source_url",
            "date",
            "title",
            "summary",
            "why_this_matters",
            "retrieval_keywords",
            "confidence",
            "last_verified_at",
            "category_ids",
            "violated_clause_ids",
            "canonical_ids",
            "outcome",
            "monetary_relief",
            "status",
            "jurisdiction",
            "retrieved_at",
        ):
            val = p.get(key)
            if val is None:
                continue
            if key in ("summary", "why_this_matters"):
                lines.append(f"    {key}: >")
                for chunk in textwrap.wrap(str(val), width=76):
                    lines.append(f"      {chunk}")
            elif key == "retrieval_keywords":
                lines.append(f"    {key}: {val}")
            elif key == "category_ids":
                lines.append(f"    category_ids: {val}")
            elif key == "violated_clause_ids":
                lines.append("    violated_clause_ids:")
                for cid in val:
                    lines.append(f"      - {cid}")
            elif key == "canonical_ids":
                lines.append("    canonical_ids:")
                for cid in val:
                    lines.append(f"      - {cid}")
            else:
                sval = str(val)
                if isinstance(val, str) and (
                    sval.startswith("$")
                    or sval.startswith(">")
                    or ":" in sval
                    or sval.startswith('"')
                    or " " in sval
                ):
                    esc = sval.replace('"', '\\"')
                    lines.append(f'    {key}: "{esc}"')
                else:
                    lines.append(f"    {key}: {val}")
        lines.append("    evidence:")
        for ev in p["evidence"]:
            lines.append("      - quote: >-")
            for chunk in textwrap.wrap(ev["quote"], width=74):
                lines.append(f"          {chunk}")
            lines.append(f"        source_url: {ev['source_url']}")
            if ev.get("section"):
                lines.append(f"        section: \"{ev['section']}\"")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n")


GAMBLING = [
    entry(
        precedent_id="prec.njdge.draftkings_self_excluded_2021",
        source="New Jersey Division of Gaming Enforcement",
        source_url="https://www.nj.gov/oag/ge/docs/Rulings/2021/feb16_28/B_7_dk_market.pdf",
        date="2021-02-24",
        title="NJ DGE v. DraftKings — marketing to self-excluded patrons",
        summary="DraftKings agreed to a $500 civil penalty after NJ DGE found it sent promotional materials to self-excluded and cooled-off patrons in violation of N.J.A.C. 13:69G-2.4(a)4.",
        why_this_matters="State gambling regulator penalty for sportsbook marketing to self-excluded consumers — core responsible-gambling ad compliance.",
        retrieval_keywords=["DraftKings", "New Jersey", "self-exclusion", "sports betting", "DGE", "responsible gambling", "marketing"],
        category_ids=["gambling", "misleading"],
        violated_clause_ids=["google.gambling.responsible", "meta.gambling.authorization_and_license"],
        canonical_ids=["gambling.responsible_gambling_required", "gambling.realmoney_requires_license_and_authorization"],
        outcome="fine",
        monetary_relief="$500",
        evidence=[{
            "quote": "The Division having sent a Notice of Violation to DraftKings Inc. on February 12, 2021 imposing a $500 civil penalty for marketing to self-excluded and cooled-off patrons in violation of a Division requirement, in violation of N.J.A.C. 13:69G-2.4(a)4.",
            "source_url": "https://www.nj.gov/oag/ge/docs/Rulings/2021/feb16_28/B_7_dk_market.pdf",
            "section": "NJ DGE Order, File Nos. D-01-20-186",
        }],
    ),
    entry(
        precedent_id="prec.njdge.draftkings_self_excluded_mail_2021",
        source="New Jersey Division of Gaming Enforcement",
        source_url="https://www.nj.gov/oag/ge/docs/Rulings/2021/mar16_31/b11_draftkings.pdf",
        date="2021-03-01",
        title="NJ DGE v. DraftKings — promotional mailings to eleven self-excluded individuals",
        summary="DraftKings paid a $10,000 civil penalty after NJ DGE found it sent promotional mailings to eleven self-excluded individuals in violation of N.J.A.C. 13:69G-2.4(b)1.",
        why_this_matters="Escalated NJ penalty for repeat self-exclusion marketing failures via direct mail.",
        retrieval_keywords=["DraftKings", "self-exclusion", "promotional mail", "New Jersey DGE", "sports betting", "$10000"],
        category_ids=["gambling", "misleading"],
        violated_clause_ids=["google.gambling.responsible", "tiktok.gambling.responsible"],
        canonical_ids=["gambling.responsible_gambling_required"],
        outcome="fine",
        monetary_relief="$10,000",
        evidence=[{
            "quote": "The Division of Gaming Enforcement having filed a complaint on March 1, 2021 against DraftKings Inc. seeking a sanction for sending promotional mailings to eleven self-excluded individuals.",
            "source_url": "https://www.nj.gov/oag/ge/docs/Rulings/2021/mar16_31/b11_draftkings.pdf",
            "section": "NJ DGE Order, File No. O-01-20-115",
        }],
    ),
    entry(
        precedent_id="prec.njdge.tipico_promotions_2025",
        source="New Jersey Division of Gaming Enforcement",
        source_url="https://www.nj.gov/oag/ge/docs/Rulings/2025/jun16_30/B7tipico.pdf",
        date="2025-06-24",
        title="NJ DGE v. Tipico — self-excluded marketing and inflated cash-out odds",
        summary="Tipico agreed to pay a $25,000 civil monetary penalty for sending promotional materials to self-excluded patrons and allowing patrons to cash out wagers at inflated odds.",
        why_this_matters="Combines responsible-gambling list violations with deceptive promotion mechanics in regulated sports betting.",
        retrieval_keywords=["Tipico", "New Jersey", "self-exclusion", "inflated odds", "sports betting", "DGE", "$25000"],
        category_ids=["gambling", "misleading"],
        violated_clause_ids=["google.gambling.responsible", "ftc.misleading.express_implied"],
        canonical_ids=["gambling.responsible_gambling_required", "misleading.missing_or_inconsistent_material_info"],
        outcome="fine",
        monetary_relief="$25,000",
        evidence=[{
            "quote": "The Division accepts the offer of Tipico to render a civil monetary penalty payment in the total amount of $25,000.",
            "source_url": "https://www.nj.gov/oag/ge/docs/Rulings/2025/jun16_30/B7tipico.pdf",
            "section": "NJ DGE Action in Lieu of Complaint, June 24, 2025",
        }],
    ),
    entry(
        precedent_id="prec.njdge.fanduel_unauthorized_promo_2025",
        source="New Jersey Division of Gaming Enforcement",
        source_url="https://www.nj.gov/oag/ge/docs/Rulings/2025/jul16_31/Summary.pdf",
        date="2025-07-16",
        title="NJ DGE v. FanDuel — unauthorized promotion penalty",
        summary="NJ DGE imposed a $2,000 civil penalty on FanDuel pursuant to a Notice of Violation for an unauthorized promotion.",
        why_this_matters="Shows state enforcement against sportsbook promotions run without regulatory authorization.",
        retrieval_keywords=["FanDuel", "New Jersey", "unauthorized promotion", "sports betting", "DGE", "$2000"],
        category_ids=["gambling"],
        violated_clause_ids=["google.gambling.certification_license", "meta.gambling.authorization_and_license"],
        canonical_ids=["gambling.realmoney_requires_license_and_authorization"],
        outcome="fine",
        monetary_relief="$2,000",
        evidence=[{
            "quote": "Imposed a $2,000 civil penalty on FanDuel pursuant to a Notice of Violation for an unauthorized promotion.",
            "source_url": "https://www.nj.gov/oag/ge/docs/Rulings/2025/jul16_31/Summary.pdf",
            "section": "Actions of the Director, July 16–31, 2025",
        }],
    ),
    entry(
        precedent_id="prec.njdge.ballys_exclusion_list_2025",
        source="New Jersey Division of Gaming Enforcement",
        source_url="https://www.nj.gov/oag/ge/docs/Rulings/2025/jul16_31/Summary.pdf",
        date="2025-07-16",
        title="NJ DGE v. Bally's Atlantic City — exclusion list violations",
        summary="NJ DGE imposed a $10,000 civil penalty against Bally's Atlantic City pursuant to an Action in Lieu of Complaint for exclusion list violations.",
        why_this_matters="Land-based casino operator penalty for failing to honor self-exclusion/exclusion list obligations relevant to gambling marketing reach.",
        retrieval_keywords=["Bally's", "Atlantic City", "exclusion list", "self-exclusion", "New Jersey DGE", "casino"],
        category_ids=["gambling"],
        violated_clause_ids=["google.gambling.responsible", "meta.gambling.no_minors"],
        canonical_ids=["gambling.responsible_gambling_required", "gambling.no_minors_targeting"],
        outcome="fine",
        monetary_relief="$10,000",
        evidence=[{
            "quote": "Imposed a $10,000 civil penalty against Bally's Atlantic City pursuant to an Action in Lieu of Complaint for exclusion list violations.",
            "source_url": "https://www.nj.gov/oag/ge/docs/Rulings/2025/jul16_31/Summary.pdf",
            "section": "Actions of the Director, July 16–31, 2025",
        }],
    ),
]

STATE_AG = [
    entry(
        precedent_id="prec.nyag.sports_betting_superbowl_2022",
        source="New York State Attorney General",
        source_url="https://ag.ny.gov/press-release/2022/consumer-alert-attorney-general-james-warns-new-yorkers-deceptive-online-sports",
        date="2022-02-10",
        title="NY AG consumer alert — deceptive online sports betting Super Bowl ads",
        summary="Attorney General James warned New Yorkers about misleading sports-betting ads touting risk-free bets and $1,000 welcome offers that often carry hidden wagering requirements and restrictions.",
        why_this_matters="Official AG guidance flagging risk-free and bonus-deposit ad patterns as deceptive in newly legal NY online sports betting.",
        retrieval_keywords=["New York AG", "sports betting", "Super Bowl", "risk-free bets", "welcome bonus", "deceptive ads"],
        category_ids=["gambling", "misleading", "financial"],
        violated_clause_ids=["ftc.misleading.express_implied", "google.gambling.responsible"],
        canonical_ids=["misleading.missing_or_inconsistent_material_info", "gambling.responsible_gambling_required"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Since online sports gambling became legal in New York last month, New Yorkers have been bombarded with misleading ads on social media and streaming sites that claim \"risk-free\" bets and \"$1,000 welcome offers,\" which sound like free money, but often come with strings attached without consumers' awareness.",
            "source_url": "https://ag.ny.gov/press-release/2022/consumer-alert-attorney-general-james-warns-new-yorkers-deceptive-online-sports",
            "section": "NY AG Consumer Alert, Feb 10, 2022",
        }],
    ),
]

FEC = [
    entry(
        precedent_id="prec.fec.ntdo_disclaimer_admonishment_2007",
        source="U.S. Federal Election Commission",
        source_url="https://www.fec.gov/updates/fec-completes-action-on-seven-enforcement-cases-two-state-parties-agree-to-civil-penalties-totaling-17000/",
        date="2007-11-19",
        title="FEC MUR 5865 — New Trier Democratic Organization inadequate disclaimers",
        summary="The FEC admonished the New Trier Democratic Organization for failing to include adequate disclaimers on a mass mailing advocating Dan Seals' 2006 congressional candidacy.",
        why_this_matters="Official FEC admonishment for missing paid-for-by disclaimers on election advocacy mail.",
        retrieval_keywords=["FEC", "MUR 5865", "disclaimer", "New Trier Democratic Organization", "Dan Seals", "mass mailing"],
        category_ids=["political"],
        violated_clause_ids=["fec.political.disclaimer", "meta.political.authorization_disclaimer"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="no_action",
        monetary_relief=None,
        evidence=[{
            "quote": "The Commission admonished NTDO for failing to include adequate disclaimers in the communication and found no reason to believe NTDO or Dan Seals for Congress violated the Act by failing to report an in-kind contribution.",
            "source_url": "https://www.fec.gov/updates/fec-completes-action-on-seven-enforcement-cases-two-state-parties-agree-to-civil-penalties-totaling-17000/",
            "section": "FEC Update, MUR 5865",
        }],
    ),
    entry(
        precedent_id="prec.fec.power_of_liberty_electioneering_2019",
        source="U.S. Federal Election Commission",
        source_url="https://www.fec.gov/updates/week-september-16-20-2019/",
        date="2019-09-20",
        title="FEC MUR 7113 — Power of Liberty electioneering communications disclosure",
        summary="Power of Liberty, Inc. agreed to pay a $6,000 civil penalty for failing to disclose electioneering communications disseminated by radio before Tennessee's 2016 Republican primary.",
        why_this_matters="501(c)(4) electioneering disclosure penalty for undisclosed radio advocacy.",
        retrieval_keywords=["FEC", "MUR 7113", "Power of Liberty", "electioneering communications", "disclosure", "radio"],
        category_ids=["political"],
        violated_clause_ids=["fec.political.disclaimer"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="civil_penalty",
        monetary_relief="$6,000",
        evidence=[{
            "quote": "The Commission entered into a conciliation agreement providing for Power of Liberty, Inc. to pay a civil penalty of $6,000.",
            "source_url": "https://www.fec.gov/updates/week-september-16-20-2019/",
            "section": "FEC Weekly Digest, MUR 7113",
        }],
    ),
    entry(
        precedent_id="prec.fec.miller_defective_disclaimer_2010",
        source="U.S. Federal Election Commission",
        source_url="https://www.fec.gov/updates/fec-takes-final-action-on-six-cases-12/",
        date="2010-08-31",
        title="FEC MUR 6274 — Matt Miller committee defective disclaimers",
        summary="The FEC dismissed a complaint against Matt Miller's Ohio congressional committee for defective disclaimers but sent a reminder letter about 2 U.S.C. § 441d and 11 C.F.R. § 110.11 disclaimer requirements.",
        why_this_matters="Illustrates FEC prosecutorial discretion on defective disclaimer materials while reaffirming statutory disclaimer rules.",
        retrieval_keywords=["FEC", "MUR 6274", "Matt Miller", "defective disclaimer", "Ohio", "441d"],
        category_ids=["political"],
        violated_clause_ids=["fec.political.disclaimer"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="no_action",
        monetary_relief=None,
        evidence=[{
            "quote": "The Commission sent a letter to the respondents, reminding them of the requirements under 2 U.S.C. § 441d and 11 C.F.R. § 110.11 concerning the use of appropriate disclaimers.",
            "source_url": "https://www.fec.gov/updates/fec-takes-final-action-on-six-cases-12/",
            "section": "FEC Update, MUR 6274",
        }],
    ),
    entry(
        precedent_id="prec.fec.schreyer_tv_disclaimer_2010",
        source="U.S. Federal Election Commission",
        source_url="https://www.fec.gov/updates/fec-takes-final-action-on-six-cases-12/",
        date="2010-08-31",
        title="FEC MUR 6283 — Manfred Schreyer TV ad without audible disclaimer",
        summary="The FEC dismissed allegations that Manfred Schreyer's congressional committee aired a television ad without an audible disclaimer, but reminded respondents of disclaimer and disclosure requirements.",
        why_this_matters="TV political ad precedent on audible disclaimer visibility and FEC reminder letters.",
        retrieval_keywords=["FEC", "MUR 6283", "television ad", "disclaimer", "Manfred Schreyer", "Ohio"],
        category_ids=["political"],
        violated_clause_ids=["fec.political.disclaimer", "google.political.paid_for_by"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="no_action",
        monetary_relief=None,
        evidence=[{
            "quote": "The Commission sent a letter to the respondents, reminding them of the requirements under the Federal Election Campaign Act of 1971, as amended, regarding appropriate disclaimers and timely filing of financial disclosure reports.",
            "source_url": "https://www.fec.gov/updates/fec-takes-final-action-on-six-cases-12/",
            "section": "FEC Update, MUR 6283",
        }],
    ),
    entry(
        precedent_id="prec.fec.nrtl_reporting_penalty_2010",
        source="U.S. Federal Election Commission",
        source_url="https://www.fec.gov/updates/fec-takes-final-action-on-six-cases-12/",
        date="2010-08-31",
        title="FEC MUR 6266 — National Right to Life PAC reporting and IE notices",
        summary="National Right to Life PAC agreed to pay a $25,000 civil penalty for failing to file timely 24- and 48-hour notices of independent expenditures and for inaccurate disclosure reports.",
        why_this_matters="Major PAC penalty for independent-expenditure reporting failures adjacent to political ad transparency.",
        retrieval_keywords=["FEC", "MUR 6266", "National Right to Life", "independent expenditure", "24-hour notice", "disclosure"],
        category_ids=["political", "financial"],
        violated_clause_ids=["fec.political.disclaimer"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="civil_penalty",
        monetary_relief="$25,000",
        evidence=[{
            "quote": "In a conciliation agreement, the respondents agreed to pay a $25,000 civil penalty, amend reports, to the extent appropriate, to correct the errors addressed in this matter.",
            "source_url": "https://www.fec.gov/updates/fec-takes-final-action-on-six-cases-12/",
            "section": "FEC Update, MUR 6266",
        }],
    ),
]

FDA_EXPANSION = [
    entry(
        precedent_id="prec.fda.curaleaf_cbd_2019",
        source="U.S. Food and Drug Administration",
        source_url="https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/curaleaf-inc-579289-07222019",
        date="2019-07-22",
        title="FDA warning — Curaleaf unapproved CBD drug claims",
        summary="FDA warned Curaleaf that CBD lotion, patch, tincture, vape pen, and pet products marketed on curaleafhemp.com and social media were unapproved new drugs sold with disease-treatment claims.",
        why_this_matters="Landmark CBD marketer warning linking social media promotion to unapproved drug and health claims.",
        retrieval_keywords=["Curaleaf", "CBD", "FDA warning letter", "unapproved drug", "health claims", "cannabis"],
        category_ids=["drugs", "health", "misleading"],
        violated_clause_ids=["google.health.unapproved_substances", "meta.atc.cbd", "ftc.health.disease_implication"],
        canonical_ids=["health.unsubstantiated_health_claims", "atc.cbd_restricted_with_certification"],
        outcome="warning_letter",
        monetary_relief=None,
        evidence=[{
            "quote": "FDA has determined that your \"CBD Lotion,\" \"CBD Pain-Relief Patch,\" \"CBD Tincture,\" and \"CBD Disposable Vape Pen\" products are unapproved new drugs sold in violation of sections 505(a) and 301(d) of the Federal Food, Drug, and Cosmetic Act.",
            "source_url": "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/curaleaf-inc-579289-07222019",
            "section": "FDA Warning Letter 579289",
        }],
    ),
    entry(
        precedent_id="prec.fda.delta8_batch_2022",
        source="U.S. Food and Drug Administration",
        source_url="https://www.fda.gov/news-events/press-announcements/fda-issues-warning-letters-companies-illegally-selling-cbd-and-delta-8-thc-products",
        date="2022-05-04",
        title="FDA batch warning — illegally marketed delta-8 THC and CBD products",
        summary="FDA issued its first warning letters for delta-8 THC products illegally marketed with unapproved therapeutic claims and added to foods such as gummies and peanut brittle.",
        why_this_matters="First FDA delta-8 enforcement wave covering intoxicating cannabinoid ads and edibles.",
        retrieval_keywords=["FDA", "delta-8 THC", "CBD", "warning letters", "gummies", "unapproved drug claims"],
        category_ids=["drugs", "health"],
        violated_clause_ids=["meta.atc.drugs_thc", "google.health.unapproved_substances", "tiktok.atc.drugs"],
        canonical_ids=["atc.recreational_drugs_and_thc_prohibited", "health.unsubstantiated_health_claims"],
        outcome="warning_letter",
        monetary_relief=None,
        evidence=[{
            "quote": "This action is the first time the FDA has issued warning letters for products containing delta-8 THC.",
            "source_url": "https://www.fda.gov/news-events/press-announcements/fda-issues-warning-letters-companies-illegally-selling-cbd-and-delta-8-thc-products",
            "section": "FDA Press Announcement, May 4, 2022",
        }],
    ),
    entry(
        precedent_id="prec.fda.cbd_food_beverage_2022",
        source="U.S. Food and Drug Administration",
        source_url="https://www.fda.gov/food/hfp-constituent-updates/fda-warns-companies-illegally-selling-food-and-beverage-products-contain-cbd",
        date="2022-11-21",
        title="FDA warning batch — CBD food and beverage products appealing to children",
        summary="FDA warned five companies for illegally selling CBD in food and beverage forms that could confuse consumers or appeal to children, including gummies and hard candies.",
        why_this_matters="FDA enforcement on CBD edibles/drink marketing intersecting youth appeal and platform ATC restrictions.",
        retrieval_keywords=["FDA", "CBD food", "CBD beverages", "gummies", "children", "warning letters"],
        category_ids=["drugs", "minors", "health"],
        violated_clause_ids=["google.health.unapproved_substances", "meta.atc.cbd", "tiktok.atc.drugs"],
        canonical_ids=["atc.cbd_restricted_with_certification", "minors.age_restricted_products_not_shown_to_minors"],
        outcome="warning_letter",
        monetary_relief=None,
        evidence=[{
            "quote": "These companies are selling CBD containing products that people may confuse for traditional foods or beverages which may result in unintentional consumption or overconsumption of CBD.",
            "source_url": "https://www.fda.gov/food/hfp-constituent-updates/fda-warns-companies-illegally-selling-food-and-beverage-products-contain-cbd",
            "section": "FDA Constituent Update, Nov 21, 2022",
        }],
    ),
]

TTB = [
    entry(
        precedent_id="prec.ttb.clean_beer_guidance_2022",
        source="U.S. Alcohol and Tobacco Tax and Trade Bureau",
        source_url="https://www.ttb.gov/public-information/news/use-of-the-word-clean-in-alcohol-beverage-labeling-and-advertising",
        date="2022-04-08",
        title="TTB guidance — misleading 'clean' claims in alcohol advertising",
        summary="TTB clarified that using 'clean' with health-benefit implications in alcohol ads — such as 'clean and healthy' or 'no headaches' — constitutes misleading health-related statements.",
        why_this_matters="Official TTB line on wellness-coded alcohol ad copy beyond McKenzie energy-claim enforcement.",
        retrieval_keywords=["TTB", "clean beer", "alcohol advertising", "misleading health claims", "wellness marketing"],
        category_ids=["alcohol", "health", "misleading"],
        violated_clause_ids=["ttb.atc.alcohol_statements"],
        canonical_ids=["atc.alcohol_mandatory_and_prohibited_statements"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "In other cases, the term is used together with other language to create the misleading impression that consumption of the alcohol beverage will have health benefits, or that the health risks otherwise associated with alcohol consumption will be mitigated.",
            "source_url": "https://www.ttb.gov/public-information/news/use-of-the-word-clean-in-alcohol-beverage-labeling-and-advertising",
            "section": "TTB Market Compliance Office, April 8, 2022",
        }],
    ),
]

DOJ = [
    entry(
        precedent_id="prec.doj.operation_in_our_sites_2010",
        source="U.S. Department of Justice",
        source_url="https://www.justice.gov/opa/speech/attorney-general-eric-holder-speaks-operation-our-sites-ii-press-conference",
        date="2010-11-29",
        title="DOJ Operation In Our Sites II — 82 counterfeit domain seizures",
        summary="DOJ and DHS executed seizure orders against 82 domain names of websites selling counterfeit goods and illegal copyrighted works on Cyber Monday 2010.",
        why_this_matters="Foundational federal IP enforcement program seizing domains used to advertise and sell counterfeits online.",
        retrieval_keywords=["Operation In Our Sites", "DOJ", "domain seizure", "counterfeit", "Cyber Monday", "trademark"],
        category_ids=["ip_trademark", "misleading"],
        violated_clause_ids=["google.ip.counterfeit_goods", "meta.ip.counterfeit_goods"],
        canonical_ids=["ip.counterfeit_goods_prohibited", "ip.third_party_ip_infringement_prohibited"],
        outcome="injunction",
        monetary_relief=None,
        evidence=[{
            "quote": "Over the past few days, the Justice Department's Criminal Division, the Department of Homeland Security and nine U.S. Attorneys' Offices from across the country obtained and executed seizure orders against 82 domain names of websites engaged in the sale and distribution of counterfeit goods and illegal copyrighted works.",
            "source_url": "https://www.justice.gov/opa/speech/attorney-general-eric-holder-speaks-operation-our-sites-ii-press-conference",
            "section": "AG Holder remarks, Operation In Our Sites II",
        }],
    ),
    entry(
        precedent_id="prec.doj.project_copycat_2012",
        source="U.S. Department of Justice / ICE HSI",
        source_url="https://www.justice.gov/archive/usao/co/news/2012/july/7-12-12.html",
        date="2012-07-12",
        title="DOJ Project Copycat — 22 look-alike counterfeit retail sites seized",
        summary="ICE HSI seized 22 websites that closely mimicked legitimate retailers to sell counterfeit merchandise as part of Project Copycat under Operation In Our Sites.",
        why_this_matters="Look-alike ecommerce ad/landing-page enforcement against sites designed to deceive consumers about brand authenticity.",
        retrieval_keywords=["Project Copycat", "Operation In Our Sites", "counterfeit websites", "look-alike sites", "ICE", "domain seizure"],
        category_ids=["ip_trademark", "misleading"],
        violated_clause_ids=["google.ip.counterfeit_goods", "meta.ip.third_party_infringement"],
        canonical_ids=["ip.counterfeit_goods_prohibited", "misleading.false_affiliation_or_endorsement"],
        outcome="injunction",
        monetary_relief=None,
        evidence=[{
            "quote": "Many of the websites so closely resembled legitimate ones that it would be difficult for even discerning consumers to tell the difference.",
            "source_url": "https://www.justice.gov/archive/usao/co/news/2012/july/7-12-12.html",
            "section": "DOJ USAO Colorado, Project Copycat",
        }],
    ),
    entry(
        precedent_id="prec.doj.ip_domain_seizures_program",
        source="U.S. Department of Justice / IPR Center",
        source_url="https://www.justice.gov/criminal/criminal-ccips/file/938316/dl?inline",
        date="2013-06-01",
        title="DOJ Operation In Our Sites — sustained counterfeit domain seizure program",
        summary="Since June 2010, federal Operation In Our Sites actions have seized more than 1,700 infringing website domain names and millions of dollars in associated proceeds.",
        why_this_matters="Program-level IP enforcement context for ads and listings driving traffic to seized counterfeit storefronts.",
        retrieval_keywords=["Operation In Our Sites", "domain seizure", "counterfeit", "IPR Center", "1700 domains", "DOJ"],
        category_ids=["ip_trademark"],
        violated_clause_ids=["google.ip.counterfeit_goods", "tiktok.ip.counterfeit_goods"],
        canonical_ids=["ip.counterfeit_goods_prohibited"],
        outcome="injunction",
        monetary_relief=">$3,000,000 seized proceeds (program total cited)",
        evidence=[{
            "quote": "Since the operation's inception, Federal law enforcement agencies, in conjunction with DOJ, have conducted 13 operations targeting sites focused on particular subject matter such as sports apparel or luxury goods and resulting in the seizure of more than 1,700 domain names of infringing websites and monetary seizures of over $3 million.",
            "source_url": "https://www.justice.gov/criminal/criminal-ccips/file/938316/dl?inline",
            "section": "2013 Joint Strategic Plan on Intellectual Property Enforcement",
        }],
    ),
]

PLATFORMS = [
    entry(
        precedent_id="prec.meta.ip_counterfeit_enforcement_2024",
        source="Meta Transparency Center",
        source_url="https://transparency.meta.com/policies/ad-standards/intellectual-property-infringement/third-party-infringement",
        date="2024-08-26",
        title="Meta ad policy — counterfeit goods rejection and proactive IP enforcement",
        summary="Meta prohibits ads promoting counterfeit goods and may reject or remove ads reported by rights holders or flagged for potential third-party IP infringement.",
        why_this_matters="Platform IP enforcement standard for ad rejection of counterfeit and infringing listings.",
        retrieval_keywords=["Meta", "counterfeit", "intellectual property", "ad rejection", "trademark", "Facebook ads"],
        category_ids=["ip_trademark"],
        violated_clause_ids=["meta.ip.counterfeit_goods", "meta.ip.third_party_infringement"],
        canonical_ids=["ip.counterfeit_goods_prohibited", "ip.third_party_ip_infringement_prohibited"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Ads may not contain content that violates the intellectual property rights of any third party, including copyright, trademark or other legal rights. This includes, but is not limited to, the promotion or sale of counterfeit goods.",
            "source_url": "https://transparency.meta.com/policies/ad-standards/intellectual-property-infringement/third-party-infringement",
            "section": "Third-Party Intellectual Property Infringement policy",
        }],
    ),
    entry(
        precedent_id="prec.meta.gambling_authorization_2024",
        source="Meta Advertising Standards",
        source_url="https://transparency.meta.com/policies/ad-standards/restricted-goods-services/gambling-games/",
        date="2024-01-01",
        title="Meta online gambling ads — authorization and licensing required",
        summary="Meta requires written authorization before running real-money online gambling ads and proof that activities are licensed or lawful in targeted territories.",
        why_this_matters="Core Meta gate for sportsbook and casino ad accounts in permitted US states.",
        retrieval_keywords=["Meta", "online gambling", "sports betting", "ad authorization", "license", "Facebook ads"],
        category_ids=["gambling"],
        violated_clause_ids=["meta.gambling.authorization_and_license", "meta.gambling.no_minors"],
        canonical_ids=["gambling.realmoney_requires_license_and_authorization", "gambling.no_minors_targeting"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Ads that promote online gambling and gaming are only allowed once an ad account has obtained authorization. Advertisers will need to request authorization from Meta through the Authorizations and Verifications tab in Meta Business Suite and provide evidence that the gambling activities are appropriately licensed by a regulator or otherwise established as lawful in the territory they want to target.",
            "source_url": "https://transparency.meta.com/policies/ad-standards/restricted-goods-services/gambling-games/",
            "section": "Restricted Goods and Services > Online Gambling and Games",
        }],
    ),
    entry(
        precedent_id="prec.google.repeat_violation_strikes_2024",
        source="Google Ads Policy",
        source_url="https://support.google.com/adspolicy/answer/10922738",
        date="2024-01-01",
        title="Google Ads — strike system for repeat policy violations",
        summary="Google issues up to three strikes for repeat violations of certain policies, with 3- and 7-day account holds followed by suspension on the third strike.",
        why_this_matters="Official Google escalation path for repeat misleading, counterfeit, or restricted-category ad violations.",
        retrieval_keywords=["Google Ads", "strikes", "repeat violations", "account suspension", "policy enforcement"],
        category_ids=["misleading"],
        violated_clause_ids=["google.misrep.unacceptable_business_practices", "google.ip.counterfeit_goods"],
        canonical_ids=["misleading.unsubstantiated_objective_claims", "ip.counterfeit_goods_prohibited"],
        outcome="suspension",
        monetary_relief=None,
        evidence=[{
            "quote": "We take repeat violations of our policies seriously and take action against advertisers for non-compliance, including disapproving violating ads so they don't serve, as well as suspending accounts for repeat or egregious violations.",
            "source_url": "https://support.google.com/adspolicy/answer/10922738",
            "section": "About enforcement procedures for repeat violations",
        }],
    ),
    entry(
        precedent_id="prec.google.counterfeit_goods_policy_2024",
        source="Google Ads Policy",
        source_url="https://support.google.com/adspolicy/answer/176017",
        date="2024-01-01",
        title="Google Ads — counterfeit goods prohibition",
        summary="Google Ads prohibits the sale or promotion of counterfeit goods that mimic brand trademarks or product features to pass as genuine.",
        why_this_matters="Primary Google ad policy cited when disapproving counterfeit product listings and landing pages.",
        retrieval_keywords=["Google Ads", "counterfeit goods", "trademark", "ad disapproval", "knockoff"],
        category_ids=["ip_trademark"],
        violated_clause_ids=["google.ip.counterfeit_goods"],
        canonical_ids=["ip.counterfeit_goods_prohibited"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Google Ads and Display & Video 360 prohibit the sale or promotion for sale of counterfeit goods.",
            "source_url": "https://support.google.com/adspolicy/answer/176017",
            "section": "Counterfeit goods policy",
        }],
    ),
    entry(
        precedent_id="prec.tiktok.h2_2020_ad_rejections",
        source="TikTok Newsroom",
        source_url="https://newsroom.tiktok.com/en-us/tiktoks-h-2-2020-transparency-report",
        date="2021-02-24",
        title="TikTok H2 2020 transparency — 3.5M ads rejected for policy violations",
        summary="TikTok rejected 3,501,477 ads in H2 2020 for violating advertising policies and guidelines, including restricted categories such as tobacco and gambling.",
        why_this_matters="Scale benchmark for TikTok proactive ad moderation across prohibited verticals.",
        retrieval_keywords=["TikTok", "transparency report", "ads rejected", "advertising policy", "3501477"],
        category_ids=["misleading", "gambling", "drugs"],
        violated_clause_ids=["tiktok.gambling.certification_license", "tiktok.atc.tobacco"],
        canonical_ids=["gambling.realmoney_requires_license_and_authorization", "atc.tobacco_and_nicotine_ads_prohibited"],
        outcome="suspension",
        monetary_relief=None,
        evidence=[{
            "quote": "3,501,477 ads were rejected for violating advertising policies and guidelines.",
            "source_url": "https://newsroom.tiktok.com/en-us/tiktoks-h-2-2020-transparency-report",
            "section": "TikTok H2 2020 Transparency Report",
        }],
    ),
    entry(
        precedent_id="prec.tiktok.gambling_certification_policy",
        source="TikTok Ads Policy",
        source_url="https://ads.tiktok.com/help/article/tiktok-ads-policy-gambling-and-games",
        date="2025-08-01",
        title="TikTok gambling ads — certification and legal-market requirements",
        summary="TikTok requires advertisers to complete certification before running gambling ads and prohibits unlicensed or illegal gambling services.",
        why_this_matters="TikTok gate parallel to Meta/Google for licensed sportsbook and casino promotions.",
        retrieval_keywords=["TikTok", "gambling ads", "certification", "sports betting", "license", "unlicensed gambling"],
        category_ids=["gambling"],
        violated_clause_ids=["tiktok.gambling.certification_license", "tiktok.gambling.responsible"],
        canonical_ids=["gambling.realmoney_requires_license_and_authorization", "gambling.responsible_gambling_required"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "To advertise gambling services, you must go through our certification process. Gambling ads are only allowed in specified markets where gambling is legal and when all local certifications and requirements are met. Gambling ads that promote unlicensed or illegal gambling services are not allowed.",
            "source_url": "https://ads.tiktok.com/help/article/tiktok-ads-policy-gambling-and-games",
            "section": "Advertising Policies > Gambling and Games > Certification requirements",
        }],
    ),
    entry(
        precedent_id="prec.linkedin.political_ads_prohibited",
        source="LinkedIn Advertising Policies",
        source_url="https://www.linkedin.com/legal/ads-policy",
        date="2024-05-28",
        title="LinkedIn — paid political advertising prohibited globally",
        summary="LinkedIn prohibits political ads including those advocating for or against candidates, parties, ballot propositions, or fundraising by political committees.",
        why_this_matters="Global political ad ban enforced through LinkedIn ad review and rejection workflow.",
        retrieval_keywords=["LinkedIn", "political ads prohibited", "election ads", "PAC", "ballot proposition"],
        category_ids=["political"],
        violated_clause_ids=["linkedin.political.prohibited"],
        canonical_ids=["political.paid_political_ads_prohibited"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Political ads are prohibited, including ads advocating for or against a particular candidate, party, ballot proposition, law, regulation, or otherwise intended to influence an election outcome.",
            "source_url": "https://www.linkedin.com/legal/ads-policy",
            "section": "LinkedIn Advertising Policies > Political",
        }],
    ),
    entry(
        precedent_id="prec.linkedin.ad_rejection_review",
        source="LinkedIn Marketing Solutions Help",
        source_url="https://www.linkedin.com/help/lms/answer/a416939",
        date="2024-05-28",
        title="LinkedIn ad review — rejection notices and appeals",
        summary="LinkedIn automatically reviews ads at launch; rejected ads display policy violation reasons in Campaign Manager with edit and appeal options.",
        why_this_matters="Documents LinkedIn enforcement workflow for prohibited categories including political, tobacco, and counterfeit content.",
        retrieval_keywords=["LinkedIn", "ad rejected", "Campaign Manager", "appeal", "ad review", "Advertising Policies"],
        category_ids=["misleading"],
        violated_clause_ids=["linkedin.finance.requirements", "linkedin.political.prohibited"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "political.paid_political_ads_prohibited"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "If an ad or Lead Gen Form's status is listed as Rejected in Campaign Manager, it means that our team reviewed your ad and found the content, landing page, or form to be in violation of our Advertising Policies.",
            "source_url": "https://www.linkedin.com/help/lms/answer/a416939",
            "section": "Ad or Lead Gen Form rejected in review",
        }],
    ),
    entry(
        precedent_id="prec.amazon.misleading_claims_moderation",
        source="Amazon Ads",
        source_url="https://advertising.amazon.com/library/guides/sponsored-brands-sponsored-display-moderation",
        date="2024-01-01",
        title="Amazon Sponsored Brands/Display — misleading claims moderation",
        summary="Amazon rejects ads with unsubstantiated superiority claims and requires ad copy to match landing-page products and offers.",
        why_this_matters="Amazon ad moderation standard for misleading superiority and landing-page mismatch claims.",
        retrieval_keywords=["Amazon Ads", "Sponsored Brands", "misleading claims", "substantiation", "ad rejection", "moderation"],
        category_ids=["misleading"],
        violated_clause_ids=["amazon.misleading.truthful_substantiated_claims", "amazon.misleading.landing_page_match"],
        canonical_ids=["misleading.unsubstantiated_objective_claims", "misleading.missing_or_inconsistent_material_info"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Your ads must be truthful and accurate, and that goes especially for any claims you make.",
            "source_url": "https://advertising.amazon.com/library/guides/sponsored-brands-sponsored-display-moderation",
            "section": "Claims and substantiations",
        }],
    ),
    entry(
        precedent_id="prec.amazon.malvertising_suspension",
        source="Amazon Ads Policy",
        source_url="https://advertising.amazon.com/resources/ad-policy/adsp-account-suspension-for-malvertising-policy",
        date="2024-01-01",
        title="Amazon DSP — account suspension for malvertising violations",
        summary="Amazon DSP may block creatives and suspend advertiser accounts for malvertising policy violations, requiring remediation before reinstatement.",
        why_this_matters="Severe Amazon Ads enforcement path for deceptive or harmful ad destinations.",
        retrieval_keywords=["Amazon DSP", "malvertising", "account suspension", "ad policy", "remediation"],
        category_ids=["misleading", "safety"],
        violated_clause_ids=["amazon.misleading.no_fake_functionality"],
        canonical_ids=["misleading.missing_or_inconsistent_material_info"],
        outcome="suspension",
        monetary_relief=None,
        evidence=[{
            "quote": "Ads, assets, destinations, and other content that violate Amazon Ads policies can be blocked by ADSP, and may result in account suspension.",
            "source_url": "https://advertising.amazon.com/resources/ad-policy/adsp-account-suspension-for-malvertising-policy",
            "section": "ADSP Account Suspension for Malvertising Policy",
        }],
    ),
    entry(
        precedent_id="prec.x.deceptive_marketing_policy",
        source="X Advertising Policies",
        source_url="https://business.x.com/en/help/ads-policies/ads-content-policies/deceptive-and-fraudulent-content",
        date="2024-01-01",
        title="X Ads — deceptive marketing and pricing omission rules",
        summary="X prohibits ads using deceptive marketing, clickbait, unjustified outcome promises, and offers that omit vital pricing or payment terms.",
        why_this_matters="Official X ad policy for misleading financial, gambling-adjacent, and subscription promotions.",
        retrieval_keywords=["X ads", "Twitter ads", "deceptive marketing", "clickbait", "pricing omission", "misleading"],
        category_ids=["misleading"],
        violated_clause_ids=["x.misleading.deceptive_marketing", "x.misleading.pricing_omission"],
        canonical_ids=["misleading.exaggerated_results", "misleading.missing_or_inconsistent_material_info"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Ads must not promote products or services using deceptive marketing or misrepresentative business practices. Examples include: Use of clickbait tactics, where the primary purpose is to drive users to a landing page through exaggerated, sensationalized, inaccurate language or calls-to-action.",
            "source_url": "https://business.x.com/en/help/ads-policies/ads-content-policies/deceptive-and-fraudulent-content",
            "section": "Ads Content Policies > Deceptive & Fraudulent Content > Deceptive marketing",
        }],
    ),
    entry(
        precedent_id="prec.meta.atc_tobacco_prohibited",
        source="Meta Advertising Standards",
        source_url="https://transparency.meta.com/policies/ad-standards/restricted-goods-services/tobacco-related-products/",
        date="2024-01-01",
        title="Meta — tobacco and nicotine product ads prohibited",
        summary="Meta prohibits ads promoting the sale or use of tobacco, nicotine, e-cigarettes, and vapes except for WHO/FDA-approved cessation products targeted to adults.",
        why_this_matters="Platform ATC enforcement baseline rejecting nicotine and vape ads including ENDS marketed on social channels.",
        retrieval_keywords=["Meta", "tobacco ads", "nicotine", "vape", "e-cigarette", "ENDS prohibited"],
        category_ids=["drugs"],
        violated_clause_ids=["meta.atc.tobacco"],
        canonical_ids=["atc.tobacco_and_nicotine_ads_prohibited"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Ads must not promote the sale or use of tobacco or nicotine products and related paraphernalia. Ads must not promote Electronic Nicotine delivery devices, such as electronic cigarettes, vaporizers, or any other products that simulate smoking or are otherwise designed for use with tobacco or nicotine products.",
            "source_url": "https://transparency.meta.com/policies/ad-standards/restricted-goods-services/tobacco-related-products/",
            "section": "Restricted Goods and Services > Tobacco and Related Products",
        }],
    ),
    entry(
        precedent_id="prec.google.gambling_minors_policy",
        source="Google Ads Policy",
        source_url="https://support.google.com/adspolicy/answer/15132179",
        date="2024-01-01",
        title="Google gambling ads — no targeting of minors",
        summary="Google requires gambling advertisers to never target minors and to include responsible-gambling information on landing pages.",
        why_this_matters="Google gambling ad gate complementing state-licensing requirements for sportsbook campaigns.",
        retrieval_keywords=["Google Ads", "gambling", "minors", "responsible gambling", "sports betting targeting"],
        category_ids=["gambling", "minors"],
        violated_clause_ids=["google.gambling.minors", "google.gambling.responsible"],
        canonical_ids=["gambling.no_minors_targeting", "gambling.responsible_gambling_required"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Gambling and online gambling-promoting content ads and destinations must also: only target approved countries, have a landing page that displays information about responsible gambling and never target minors.",
            "source_url": "https://support.google.com/adspolicy/answer/15132179",
            "section": "Advertising Policies > Gambling and games > Requirements",
        }],
    ),
]

FINRA = [
    entry(
        precedent_id="prec.finra.robinhood_finfluencer_2025",
        source="Financial Industry Regulatory Authority (FINRA)",
        source_url="https://www.finra.org/media-center/newsreleases/2025/finra-orders-robinhood-financial-pay-375-million-restitution",
        date="2025-03-07",
        title="FINRA v. Robinhood — unsupervised paid finfluencer communications",
        summary="FINRA fined Robinhood entities $26 million and ordered $3.75 million restitution, finding Robinhood failed to reasonably supervise paid social media influencer posts that were promissory or not fair and balanced.",
        why_this_matters="Major finfluencer supervision penalty extending M1 Finance precedent to promissory social-media financial ads.",
        retrieval_keywords=["Robinhood", "FINRA", "finfluencer", "social media", "fair and balanced", "Rule 2210"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["finra.finance.fair_balanced", "finra.finance.no_performance_projection"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.testimonials_endorsements_disclosure"],
        outcome="fine",
        monetary_relief="$26,000,000 fines; $3,750,000 restitution",
        evidence=[{
            "quote": "Robinhood Financial failed to reasonably supervise and retain social media communications promoting the firm that were posted by paid social media influencers. Some of these communications included statements that were promissory or not fair and balanced, and thus misleading to investors.",
            "source_url": "https://www.finra.org/media-center/newsreleases/2025/finra-orders-robinhood-financial-pay-375-million-restitution",
            "section": "FINRA News Release, March 7, 2025",
        }],
    ),
]

CFPB = [
    entry(
        precedent_id="prec.cfpb.freedom_debt_relief_2019",
        source="Consumer Financial Protection Bureau",
        source_url="https://files.consumerfinance.gov/f/documents/cfpb_freedom-debt-relief_stipulated-final-judgment-order_2019-07.pdf",
        date="2019-07-01",
        title="CFPB v. Freedom Debt Relief — deceptive debt-relief marketing",
        summary="Freedom Debt Relief agreed to a $5 million civil penalty and $20 million restitution order prohibiting misrepresentations about creditor negotiations and fee charges in debt-relief advertising and sales.",
        why_this_matters="Landmark debt-relief ad enforcement on misrepresentation and advance-fee practices.",
        retrieval_keywords=["Freedom Debt Relief", "CFPB", "debt relief", "deceptive marketing", "Telemarketing Sales Rule", "advance fees"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["cfpb.finance.actually_available_terms", "cfpb.finance.trigger_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.credit_advertising_trigger_terms"],
        outcome="consent_order",
        monetary_relief="$5,000,000 penalty; $20,000,000 restitution",
        evidence=[{
            "quote": "The Company Defendant and its officers, agents, servants, employees, and attorneys, in connection with the advertising, marketing, promotion, offering for sale, sale, or provision of Debt-Relief Services, may not misrepresent, or assist others in misrepresenting, expressly or impliedly.",
            "source_url": "https://files.consumerfinance.gov/f/documents/cfpb_freedom-debt-relief_stipulated-final-judgment-order_2019-07.pdf",
            "section": "Stipulated Final Judgment, Section I",
        }],
    ),
    entry(
        precedent_id="prec.cfpb.western_benefits_2024",
        source="Consumer Financial Protection Bureau",
        source_url="https://www.consumerfinance.gov/about-us/newsroom/cfpb-takes-action-against-western-benefits-for-swindling-student-loan-borrowers/",
        date="2024-05-20",
        title="CFPB v. Western Benefits Group — deceptive student-loan debt-relief ads",
        summary="CFPB ordered Western Benefits to cease operations and pay a $400,000 penalty for charging illegal advance fees and falsely claiming Department of Education affiliation in debt-relief marketing.",
        why_this_matters="Recent CFPB penalty for false government-affiliation claims in student-loan relief advertising.",
        retrieval_keywords=["Western Benefits", "CFPB", "student loans", "debt relief", "advance fees", "Department of Education affiliation"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["cfpb.finance.actually_available_terms", "linkedin.finance.prohibited"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "misleading.false_affiliation_or_endorsement"],
        outcome="consent_order",
        monetary_relief="$400,000",
        evidence=[{
            "quote": "The CFPB found Western Benefits also misrepresented that it was affiliated with and endorsed by the Department of Education, and that the company would help consumers consolidate student loans, lower consumers' monthly student loan payments, or obtain loan cancellation.",
            "source_url": "https://www.consumerfinance.gov/about-us/newsroom/cfpb-takes-action-against-western-benefits-for-swindling-student-loan-borrowers/",
            "section": "CFPB Press Release, May 20, 2024",
        }],
    ),
]


def verify_clauses(precedents: list[dict]) -> None:
    clause_ids = set()
    for path in (ROOT / "corpus").glob("*.yaml"):
        doc = yaml.safe_load(path.read_text()) or {}
        for c in doc.get("clauses", []) or []:
            clause_ids.add(c["id"])
    for p in precedents:
        for cid in p.get("violated_clause_ids", []) or []:
            if cid not in clause_ids:
                raise SystemExit(f"Unknown clause {cid} in {p['precedent_id']}")


def merge_precedents(path: Path, new_entries: list[dict]) -> list[dict]:
    if path.exists():
        doc = yaml.safe_load(path.read_text()) or {}
        existing = doc.get("precedents", []) or []
    else:
        existing = []
    existing_ids = {p["precedent_id"] for p in existing}
    for e in new_entries:
        if e["precedent_id"] in existing_ids:
            raise SystemExit(f"Duplicate precedent_id {e['precedent_id']} in {path}")
    return existing + new_entries


def main() -> None:
    all_new = (
        GAMBLING
        + STATE_AG
        + FEC
        + FDA_EXPANSION
        + TTB
        + DOJ
        + PLATFORMS
        + FINRA
        + CFPB
    )
    verify_clauses(all_new)
    print(f"Generating {len(all_new)} Phase 2 precedents")

    dump_file(PREC / "gambling.yaml", "# NJ DGE and state gambling advertising enforcement.", GAMBLING)
    dump_file(PREC / "state_ag.yaml", "# State Attorney General enforcement precedents.", merge_precedents(PREC / "state_ag.yaml", STATE_AG))
    dump_file(PREC / "fec.yaml", "# FEC political advertising precedents.", merge_precedents(PREC / "fec.yaml", FEC))
    dump_file(PREC / "fda_expansion.yaml", "# FDA tobacco/ENDS/cannabis enforcement — Phase 1+2 expansion.", merge_precedents(PREC / "fda_expansion.yaml", FDA_EXPANSION))
    dump_file(PREC / "ttb.yaml", "# TTB alcohol advertising enforcement.", merge_precedents(PREC / "ttb.yaml", TTB))
    dump_file(PREC / "doj.yaml", "# DOJ enforcement precedents (non-HUD seed cases).", merge_precedents(PREC / "doj.yaml", DOJ))
    dump_file(PREC / "platforms.yaml", "# Platform policy enforcement precedents (official transparency/policy pages).", merge_precedents(PREC / "platforms.yaml", PLATFORMS))
    dump_file(PREC / "finra.yaml", "# FINRA enforcement precedents.", merge_precedents(PREC / "finra.yaml", FINRA))
    dump_file(PREC / "cfpb.yaml", "# CFPB enforcement precedents.", merge_precedents(PREC / "cfpb.yaml", CFPB))


if __name__ == "__main__":
    main()
