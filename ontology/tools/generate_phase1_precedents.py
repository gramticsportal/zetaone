#!/usr/bin/env python3
"""Generate Phase 1 precedent YAML sidecars. Run once, then delete or keep for audit."""
from __future__ import annotations

import textwrap
from pathlib import Path

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


FTC_EXPANSION = [
    entry(
        precedent_id="prec.ftc.facebook_privacy_2019",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2019/07/ftc-imposes-5-billion-penalty-sweeping-new-privacy-restrictions-facebook",
        date="2019-07-24",
        title="FTC v. Facebook — record $5B privacy penalty and conduct relief",
        summary="Facebook agreed to pay a record $5 billion civil penalty and accept sweeping privacy restrictions after the FTC found it deceived users about control over personal information in violation of a 2012 order.",
        why_this_matters="Landmark privacy enforcement setting the penalty baseline for targeted-ad and data-sharing violations at platform scale.",
        retrieval_keywords=["Facebook", "Meta", "privacy", "5 billion", "COPPA-adjacent data", "targeted advertising", "consent order"],
        category_ids=["privacy", "misleading"],
        violated_clause_ids=["ccpa.privacy.opt_out_sale_sharing"],
        canonical_ids=["privacy.opt_out_of_sale_or_sharing_for_targeted_ads"],
        outcome="civil_penalty",
        monetary_relief="$5,000,000,000",
        evidence=[{
            "quote": "Despite repeated promises to its billions of users worldwide that they could control how their personal information is shared, Facebook undermined consumers' choices.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2019/07/ftc-imposes-5-billion-penalty-sweeping-new-privacy-restrictions-facebook",
            "section": "FTC Press Release, July 24, 2019",
        }],
    ),
    entry(
        precedent_id="prec.ftc.goodrx_health_data_2023",
        source="U.S. Federal Trade Commission / U.S. Department of Justice",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2023/02/ftc-enforcement-action-bar-goodrx-sharing-consumers-sensitive-health-info-advertising",
        date="2023-02-01",
        title="FTC/DOJ v. GoodRx — health data shared with ad platforms",
        summary="GoodRx agreed to pay $1.5 million and is permanently barred from sharing user health data with third parties for advertising after the FTC alleged it deceptively promised privacy while sharing prescription and condition data with Facebook, Google, and others.",
        why_this_matters="First FTC Health Breach Notification Rule case; models health-adjacent retargeting and sensitive-attribute misuse in ads.",
        retrieval_keywords=["GoodRx", "health data", "Facebook ads", "Google ads", "prescription", "retargeting", "HIPAA-adjacent"],
        category_ids=["health", "privacy", "misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "ftc.health.material_safety_disclosure"],
        canonical_ids=["health.health_privacy_sensitive_attributes", "privacy.sensitive_attribute_targeting_prohibited"],
        outcome="civil_penalty",
        monetary_relief="$1,500,000",
        evidence=[{
            "quote": "GoodRx repeatedly violated this promise by sharing sensitive personal health information—including its users' prescription medications and personal health conditions—with third party advertising companies and advertising platforms like Facebook, Google, and Criteo.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2023/02/ftc-enforcement-action-bar-goodrx-sharing-consumers-sensitive-health-info-advertising",
            "section": "FTC Press Release, Feb 1, 2023",
        }],
    ),
    entry(
        precedent_id="prec.ftc.microsoft_xbox_coppa_2023",
        source="U.S. Federal Trade Commission / U.S. Department of Justice",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2023/06/ftc-will-require-microsoft-pay-20-million-over-charges-it-illegally-collected-personal-information",
        date="2023-06-05",
        title="FTC/DOJ v. Microsoft (Xbox) — COPPA children's data collection",
        summary="Microsoft agreed to pay $20 million to settle FTC charges that Xbox collected and retained children's personal information without parental notice or consent, violating COPPA.",
        why_this_matters="Clarifies COPPA coverage of gaming avatars/biometrics and third-party publisher data sharing in youth-facing products.",
        retrieval_keywords=["Microsoft", "Xbox", "COPPA", "children", "gaming", "parental consent", "avatars"],
        category_ids=["minors", "privacy"],
        violated_clause_ids=["ftc.minors.coppa_parental_consent"],
        canonical_ids=["minors.parental_consent_for_childrens_data"],
        outcome="civil_penalty",
        monetary_relief="$20,000,000",
        evidence=[{
            "quote": "Microsoft will pay $20 million to settle Federal Trade Commission charges that it violated the Children's Online Privacy Protection Act (COPPA) by collecting personal information from children who signed up to its Xbox gaming system without notifying their parents or obtaining their parents' consent.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2023/06/ftc-will-require-microsoft-pay-20-million-over-charges-it-illegally-collected-personal-information",
            "section": "FTC Press Release, June 5, 2023",
        }],
    ),
    entry(
        precedent_id="prec.ftc.chegg_data_security_2023",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2023/01/ftc-finalizes-order-ed-tech-provider-chegg-lax-security-exposed-student-data",
        date="2023-01-26",
        title="FTC v. Chegg — student data breaches and retention failures",
        summary="The FTC finalized an order against Chegg for lax security that exposed sensitive data of about 40 million users and employees across four breaches, requiring data minimization and user deletion rights.",
        why_this_matters="Ed-tech precedent for data minimization and deletion obligations relevant to ad-tech data pipelines targeting students.",
        retrieval_keywords=["Chegg", "student data", "data breach", "edtech", "privacy", "scholarship data", "retention"],
        category_ids=["privacy", "minors"],
        violated_clause_ids=["tiktok.privacy.data_collection_disclosure"],
        canonical_ids=["privacy.data_collection_disclosure_required"],
        outcome="consent_order",
        monetary_relief=None,
        evidence=[{
            "quote": "Chegg failed to protect the personal information it collected from users and employees. For example, the company stored users' personal data on its cloud storage databases in plain text and, until at least 2018, employed outdated and weak encryption to protect user passwords.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2023/01/ftc-finalizes-order-ed-tech-provider-chegg-lax-security-exposed-student-data",
            "section": "FTC Press Release, Jan 26, 2023",
        }],
    ),
    entry(
        precedent_id="prec.ftc.intuit_turbotax_free_2022",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/system/files/ftc_gov/pdf/intuit_initial_decision_public_redacted_1.pdf",
        date="2022-05-04",
        title="FTC v. Intuit — deceptive TurboTax 'free' filing campaign",
        summary="The FTC found Intuit deceptively marketed TurboTax as free for all consumers when only some filers qualified, following a parallel $141 million multistate settlement restricting 'Free, Free, Free' ads.",
        why_this_matters="Canonical 'free' offer deception case for financial and lead-gen ads with hidden eligibility gates.",
        retrieval_keywords=["Intuit", "TurboTax", "free filing", "deceptive advertising", "dark patterns", "tax prep"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "cfpb.finance.actually_available_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "misleading.unsubstantiated_objective_claims"],
        outcome="consent_order",
        monetary_relief="$141,000,000 (multistate consumer redress, parallel)",
        evidence=[{
            "quote": "The Complaint alleges that Respondent repeatedly claimed through various advertising channels that consumers could file their taxes for free using TurboTax, when in fact, TurboTax is free for only some consumers, based on the tax filing forms used.",
            "source_url": "https://www.ftc.gov/system/files/ftc_gov/pdf/intuit_initial_decision_public_redacted_1.pdf",
            "section": "FTC Initial Decision, D09408 (public redacted)",
        }],
    ),
    entry(
        precedent_id="prec.ftc.herbalife_mlm_2016",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2016/07/herbalife-will-restructure-its-multi-level-marketing-operations-pay-200-million-consumer-redress",
        date="2016-07-15",
        title="FTC v. Herbalife — deceptive earnings claims in MLM marketing",
        summary="Herbalife agreed to pay $200 million and restructure its U.S. business after the FTC charged it deceived distributors with unfounded income promises and an unfair compensation structure rewarding recruitment over retail sales.",
        why_this_matters="Major earnings-claim and income-opportunity advertising precedent for finance and influencer marketing.",
        retrieval_keywords=["Herbalife", "MLM", "earnings claims", "income opportunity", "deceptive advertising", "200 million"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["ftc.finance.earnings_claims", "ftc.misleading.reasonable_basis"],
        canonical_ids=["finance.performance_claims_substantiation", "misleading.unsubstantiated_objective_claims"],
        outcome="settlement",
        monetary_relief="$200,000,000",
        evidence=[{
            "quote": "The settlement also prohibits Herbalife from misrepresenting distributors' potential or likely earnings. The order specifically prohibits Herbalife from claiming that members can 'quit their job' or otherwise enjoy a lavish lifestyle.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2016/07/herbalife-will-restructure-its-multi-level-marketing-operations-pay-200-million-consumer-redress",
            "section": "FTC Press Release, July 15, 2016",
        }],
    ),
    entry(
        precedent_id="prec.ftc.weight_watchers_kurbo_coppa_2022",
        source="U.S. Federal Trade Commission / U.S. Department of Justice",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2022/03/ftc-takes-action-against-company-formerly-known-weight-watchers-illegally-collecting-kids-sensitive",
        date="2022-03-04",
        title="FTC/DOJ v. WW/Kurbo — COPPA violations in kids' weight-loss app",
        summary="WW International and Kurbo agreed to pay $1.5 million, delete illegally collected children's data, and destroy algorithms trained on that data after marketing a weight-loss app to children as young as eight without parental consent.",
        why_this_matters="Links minors' health apps, body-image marketing, and COPPA consent failures—highly relevant to youth-targeted wellness ads.",
        retrieval_keywords=["Weight Watchers", "Kurbo", "COPPA", "children", "weight loss app", "health data", "minors"],
        category_ids=["minors", "health", "privacy"],
        violated_clause_ids=["ftc.minors.coppa_parental_consent"],
        canonical_ids=["minors.parental_consent_for_childrens_data", "health.negative_self_perception_body_image"],
        outcome="civil_penalty",
        monetary_relief="$1,500,000",
        evidence=[{
            "quote": "WW International, Inc., formerly known as Weight Watchers, and a subsidiary called Kurbo, Inc., marketed a weight loss app for use by children as young as eight and then collected their personal information without parental permission.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2022/03/ftc-takes-action-against-company-formerly-known-weight-watchers-illegally-collecting-kids-sensitive",
            "section": "FTC Press Release, March 4, 2022",
        }],
    ),
    entry(
        precedent_id="prec.ftc.att_unlimited_data_2019",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2019/11/att-pay-60-million-resolve-ftc-allegations-it-misled-consumers-unlimited-data-promises",
        date="2019-11-05",
        title="FTC v. AT&T — deceptive 'unlimited' data advertising",
        summary="AT&T agreed to pay $60 million to settle FTC allegations it charged millions of customers for unlimited data plans while secretly throttling speeds after modest usage thresholds.",
        why_this_matters="Classic material-omission case for telecom and subscription ads promising unlimited service.",
        retrieval_keywords=["AT&T", "unlimited data", "throttling", "deceptive advertising", "material omission", "wireless"],
        category_ids=["misleading"],
        violated_clause_ids=["ftc.misleading.express_implied", "ftc.misleading.reasonable_basis"],
        canonical_ids=["misleading.missing_or_inconsistent_material_info", "misleading.unsubstantiated_objective_claims"],
        outcome="settlement",
        monetary_relief="$60,000,000",
        evidence=[{
            "quote": "AT&T Mobility, LLC, will pay $60 million to settle litigation with the Federal Trade Commission over allegations that the wireless provider misled millions of its smartphone customers by charging them for 'unlimited' data plans while reducing their data speeds.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2019/11/att-pay-60-million-resolve-ftc-allegations-it-misled-consumers-unlimited-data-promises",
            "section": "FTC Press Release, Nov 5, 2019",
        }],
    ),
    entry(
        precedent_id="prec.ftc.mediaalpha_insurance_leads_2025",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2025/08/assurance-iq-mediaalpha-pay-total-145-million-settle-ftc-charges-they-misled-consumers-seeking",
        date="2025-08-07",
        title="FTC v. MediaAlpha — deceptive health-insurance lead generation",
        summary="MediaAlpha agreed to a $45 million judgment for operating misleading lead-gen sites like ObamacarePlans.com that implied government affiliation and sold consumer data to telemarketers pushing non-ACA plans.",
        why_this_matters="Major lead-gen and impersonation precedent for insurance and financial comparison ads.",
        retrieval_keywords=["MediaAlpha", "ObamacarePlans", "health insurance leads", "lead generation", "government impersonation", "robocalls"],
        category_ids=["financial", "health", "misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "ftc.misleading.express_implied"],
        canonical_ids=["misleading.false_affiliation_or_endorsement", "finance.misleading_or_unbalanced_claims"],
        outcome="settlement",
        monetary_relief="$45,000,000",
        evidence=[{
            "quote": "MediaAlpha has attracted consumers to their healthcare-related lead generation websites using misleading domains such as 'ObamacarePlans.com' that imply they are associated with the government and claim that consumers will be able to buy low-cost, comprehensive health insurance that complies with the ACA.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2025/08/assurance-iq-mediaalpha-pay-total-145-million-settle-ftc-charges-they-misled-consumers-seeking",
            "section": "FTC Press Release, Aug 7, 2025",
        }],
    ),
    entry(
        precedent_id="prec.ftc.assurance_iq_insurance_2025",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/system/files/ftc_gov/pdf/Assurance-Complaint.pdf",
        date="2025-08-07",
        title="FTC v. Assurance IQ — misrepresented ACA-compliant health coverage",
        summary="Assurance IQ faced a $100 million judgment in a parallel FTC action for misleading consumers into buying short-term and limited-benefit plans while representing them as comprehensive ACA-compliant insurance.",
        why_this_matters="Pairs with MediaAlpha to show full-funnel deception from lead ads through telemarketing close.",
        retrieval_keywords=["Assurance IQ", "STM plans", "ACA compliance", "health insurance advertising", "telemarketing", "limited benefit"],
        category_ids=["financial", "health", "misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "ftc.health.disease_implication"],
        canonical_ids=["health.unsubstantiated_health_claims", "misleading.unsubstantiated_objective_claims"],
        outcome="settlement",
        monetary_relief="$100,000,000",
        evidence=[{
            "quote": "The above representations are deceptive because: (a) many of the STM and LBI plans sold by Assurance were not ACA-compliant, comprehensive health insurance or the equivalent of such health insurance.",
            "source_url": "https://www.ftc.gov/system/files/ftc_gov/pdf/Assurance-Complaint.pdf",
            "section": "FTC Complaint, Assurance IQ (Aug 2025)",
        }],
    ),
    entry(
        precedent_id="prec.ftc.bountiful_review_hijacking_2023",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2023/02/ftc-charges-supplement-marketer-hijacking-ratings-reviews-amazoncom-using-them-deceive-consumers",
        date="2023-02-16",
        title="FTC v. Bountiful Company — Amazon review hijacking",
        summary="The Bountiful Company agreed to pay $600,000 in the FTC's first case challenging review hijacking—merging new Amazon listings with established products to steal ratings, reviews, and badges.",
        why_this_matters="First enforcement against manipulated social proof used in ecommerce and marketplace ads.",
        retrieval_keywords=["Bountiful", "Amazon reviews", "review hijacking", "fake social proof", "Best Seller badge", "supplements"],
        category_ids=["misleading", "ip_trademark"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "amazon.misleading.truthful_substantiated_claims"],
        canonical_ids=["misleading.false_affiliation_or_endorsement", "misleading.unsubstantiated_objective_claims"],
        outcome="settlement",
        monetary_relief="$600,000",
        evidence=[{
            "quote": "The case against Bountiful marks the FTC's first law enforcement challenging 'review hijacking,' in which a marketer steals or repurposes reviews of another product.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2023/02/ftc-charges-supplement-marketer-hijacking-ratings-reviews-amazoncom-using-them-deceive-consumers",
            "section": "FTC Press Release, Feb 16, 2023",
        }],
    ),
    entry(
        precedent_id="prec.ftc.evoke_wellness_google_ads_2025",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2025/01/ftc-sues-evoke-wellness-top-executives-misleading-consumers-seeking-substance-use-disorder-treatment",
        date="2025-01-16",
        title="FTC v. Evoke Wellness — deceptive Google search ads impersonating clinics",
        summary="The FTC sued Evoke Wellness for using deceptive Google search ads and telemarketing to impersonate other substance-use treatment providers, funneling at least 3,500 misled callers to its call center.",
        why_this_matters="Shows paid-search ad impersonation enforcement in a regulated health vertical.",
        retrieval_keywords=["Evoke Wellness", "Google search ads", "healthcare impersonation", "treatment clinic", "paid search", "telemarketing"],
        category_ids=["health", "misleading"],
        violated_clause_ids=["google.misrep.unacceptable_business_practices", "ftc.health.disease_implication"],
        canonical_ids=["misleading.false_affiliation_or_endorsement", "health.unsubstantiated_health_claims"],
        outcome="court_order",
        monetary_relief=None,
        evidence=[{
            "quote": "Evoke tricked consumers into contacting Evoke's call center by using deceptive Google search ads that appeared to be from the specific substance use disorder treatment clinics searched for by consumers.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2025/01/ftc-sues-evoke-wellness-top-executives-misleading-consumers-seeking-substance-use-disorder-treatment",
            "section": "FTC Press Release, Jan 16, 2025",
        }],
    ),
]

# Verify amazon clause exists
SEC_EXPANSION = [
    entry(
        precedent_id="prec.sec.paul_pierce_crypto_2023",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/newsroom/press-releases/2023-34",
        date="2023-02-17",
        title="SEC v. Paul Pierce — undisclosed crypto touting and misleading tweets",
        summary="Paul Pierce settled SEC charges for promoting EMAX tokens without disclosing $244,000+ in compensation and for misleading tweets about his holdings, paying $1.409 million total.",
        why_this_matters="High-profile influencer/crypto ad disclosure case under securities anti-touting rules.",
        retrieval_keywords=["Paul Pierce", "crypto", "EMAX", "influencer", "undisclosed payment", "touting", "Twitter"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["sec.finance.testimonials", "sec.finance.untrue_or_unbalanced"],
        canonical_ids=["finance.testimonials_endorsements_disclosure", "finance.misleading_or_unbalanced_claims"],
        outcome="settlement",
        monetary_relief="$1,409,000",
        evidence=[{
            "quote": "The SEC's order finds that Pierce failed to disclose that he was paid more than $244,000 worth of EMAX tokens to promote the tokens on Twitter.",
            "source_url": "https://www.sec.gov/newsroom/press-releases/2023-34",
            "section": "SEC Press Release 2023-34",
        }],
    ),
    entry(
        precedent_id="prec.sec.lindsay_lohan_crypto_2023",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/files/litigation/admin/2023/33-11173.pdf",
        date="2023-03-22",
        title="SEC v. Lindsay Lohan — undisclosed TRX crypto promotion",
        summary="Lindsay Lohan settled SEC charges for promoting Tronix (TRX) on Twitter without disclosing $10,000 compensation from the issuer.",
        why_this_matters="Celebrity paid-promotion disclosure template for crypto and fintech social ads.",
        retrieval_keywords=["Lindsay Lohan", "TRX", "Tron", "crypto touting", "Section 17(b)", "influencer disclosure"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["sec.finance.testimonials"],
        canonical_ids=["finance.testimonials_endorsements_disclosure"],
        outcome="settlement",
        monetary_relief="$40,670 (disgorgement, interest, penalty)",
        evidence=[{
            "quote": "Lohan did not disclose that she was being paid to give publicity to such security by the entity offering and selling it to the public.",
            "source_url": "https://www.sec.gov/files/litigation/admin/2023/33-11173.pdf",
            "section": "SEC Admin Proceeding 33-11173",
        }],
    ),
    entry(
        precedent_id="prec.sec.jake_paul_crypto_2023",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/files/litigation/admin/2023/33-11171.pdf",
        date="2023-03-22",
        title="SEC v. Jake Paul — undisclosed TRX crypto promotion",
        summary="Jake Paul settled SEC charges for touting TRX on Twitter without disclosing approximately $25,019 in crypto compensation from Tron.",
        why_this_matters="Demonstrates SEC enforcement against social-media promoters paid in tokens rather than cash.",
        retrieval_keywords=["Jake Paul", "TRX", "crypto influencer", "paid promotion", "undisclosed compensation"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["sec.finance.testimonials"],
        canonical_ids=["finance.testimonials_endorsements_disclosure"],
        outcome="settlement",
        monetary_relief="$103,000 (approx. disgorgement, interest, penalty)",
        evidence=[{
            "quote": "Paul did not disclose that he was being paid to give publicity to such security by the entity offering and selling it to the public.",
            "source_url": "https://www.sec.gov/files/litigation/admin/2023/33-11171.pdf",
            "section": "SEC Admin Proceeding 33-11171",
        }],
    ),
    entry(
        precedent_id="prec.sec.justin_sun_celebrity_touting_2023",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/newsroom/press-releases/2023-59",
        date="2023-03-22",
        title="SEC v. Justin Sun et al. — paid celebrity crypto touting scheme",
        summary="The SEC charged Justin Sun and companies with fraud and unregistered TRX/BTT offerings, alleging an orchestrated scheme to pay celebrities to tout tokens without disclosure; eight celebrities settled related charges.",
        why_this_matters="Landmark case connecting issuer marketing programs to influencer ad disclosure failures at scale.",
        retrieval_keywords=["Justin Sun", "TRX", "BTT", "celebrity crypto ads", "paid touting", "wash trading"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["sec.finance.testimonials", "sec.finance.untrue_or_unbalanced"],
        canonical_ids=["finance.testimonials_endorsements_disclosure", "finance.crypto_restricted"],
        outcome="court_order",
        monetary_relief=">$400,000 (celebrity settlements aggregate)",
        evidence=[{
            "quote": "The SEC also charged Sun and his companies with fraudulently manipulating the secondary market for TRX through extensive wash trading, and for orchestrating a scheme to pay celebrities to tout TRX and BTT without disclosing their compensation.",
            "source_url": "https://www.sec.gov/newsroom/press-releases/2023-59",
            "section": "SEC Press Release 2023-59",
        }],
    ),
    entry(
        precedent_id="prec.sec.austin_mahone_touting_2023",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/enforcement-litigation/litigation-releases/lr-25803",
        date="2023-08-04",
        title="SEC v. Austin Mahone — illegal crypto touting settlement",
        summary="The SEC obtained a consent judgment against Austin Mahone for illegally touting TRX and BTT without disclosing compensation, including a three-year bar on paid crypto touting.",
        why_this_matters="Shows post-settlement conduct restrictions applied to celebrity crypto promoters.",
        retrieval_keywords=["Austin Mahone", "crypto touting", "TRX", "BTT", "celebrity endorsement", "disclosure"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["sec.finance.testimonials"],
        canonical_ids=["finance.testimonials_endorsements_disclosure"],
        outcome="settlement",
        monetary_relief="$45,724 (disgorgement, interest, penalty)",
        evidence=[{
            "quote": "The SEC obtained a final judgment resolving the SEC's action against defendant Austin Mahone, who the SEC previously charged with illegally touting crypto asset securities Tronix (TRX) and BitTorrent (BTT) without disclosing his compensation.",
            "source_url": "https://www.sec.gov/enforcement-litigation/litigation-releases/lr-25803",
            "section": "SEC Litigation Release 25803",
        }],
    ),
]

CFPB = [
    entry(
        precedent_id="prec.cfpb.navy_federal_overdraft_2024",
        source="Consumer Financial Protection Bureau",
        source_url="https://www.consumerfinance.gov/about-us/newsroom/cfpb-orders-navy-federal-credit-union-to-pay-more-than-95-million-for-illegal-surprise-overdraft-fees/",
        date="2024-11-07",
        title="CFPB v. Navy Federal — surprise overdraft fee practices",
        summary="The CFPB ordered Navy Federal to pay more than $95 million for unfair overdraft fees on authorized-positive transactions and delayed posting of person-to-person credits.",
        why_this_matters="Major 'junk fee' precedent for misleading financial product terms in marketing and servicing.",
        retrieval_keywords=["Navy Federal", "overdraft fees", "surprise fees", "CFPB", "unfair practices", "banking"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["cfpb.finance.actually_available_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims"],
        outcome="consent_order",
        monetary_relief=">$95,000,000",
        evidence=[{
            "quote": "Respondent committed unfair acts and practices when it collected overdraft fees from consumers on transactions that had a sufficient balance at the time Respondent authorized the transaction but then later settled with an insufficient balance.",
            "source_url": "https://files.consumerfinance.gov/f/documents/cfpb_navy-federal-credit-union-consent-order_2024-11.pdf",
            "section": "CFPB Consent Order 2024-CFPB-0014",
        }],
    ),
    entry(
        precedent_id="prec.cfpb.edfinancial_pslf_2022",
        source="Consumer Financial Protection Bureau",
        source_url="https://www.consumerfinance.gov/about-us/newsroom/cfpb-sanctions-edfinancial-for-lying-about-student-loan-cancellation/",
        date="2022-03-30",
        title="CFPB v. Edfinancial — deceptive student loan forgiveness guidance",
        summary="Edfinancial paid a $1 million penalty for deceptive statements to FFELP borrowers about Public Service Loan Forgiveness eligibility and consolidation options.",
        why_this_matters="Servicer misrepresentation precedent applicable to education-finance advertising and customer communications.",
        retrieval_keywords=["Edfinancial", "PSLF", "student loans", "loan forgiveness", "deceptive statements", "FFELP"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["cfpb.finance.actually_available_terms", "cfpb.finance.trigger_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.credit_advertising_trigger_terms"],
        outcome="consent_order",
        monetary_relief="$1,000,000",
        evidence=[{
            "quote": "When FFELP borrowers asked about forgiveness options available to them, Edfinancial representatives often described forgiveness options available only for FFELP loans and failed to mention PSLF.",
            "source_url": "https://www.consumerfinance.gov/about-us/newsroom/cfpb-sanctions-edfinancial-for-lying-about-student-loan-cancellation/",
            "section": "CFPB Press Release, March 30, 2022",
        }],
    ),
    entry(
        precedent_id="prec.cfpb.rmk_mortgage_ads_2023",
        source="Consumer Financial Protection Bureau",
        source_url="https://files.consumerfinance.gov/f/documents/cfpb_spring-semi-annual-report_2023-11.pdf",
        date="2023-02-27",
        title="CFPB v. RMK Financial — repeat deceptive mortgage advertisements",
        summary="The CFPB permanently banned RMK Financial from mortgage lending after finding it sent millions of deceptive mortgage ads violating a 2015 consent order, including false VA/FHA affiliation implications.",
        why_this_matters="Repeat-offender mortgage ad case illustrating Reg N / TILA trigger-term and affiliation deception.",
        retrieval_keywords=["RMK Financial", "mortgage ads", "VA FHA", "deceptive advertising", "Reg N", "Majestic Home Loans"],
        category_ids=["financial", "misleading", "discrimination"],
        violated_clause_ids=["cfpb.finance.mortgage_prohibited_acts", "cfpb.finance.trigger_terms"],
        canonical_ids=["finance.mortgage_advertising_prohibited_acts", "misleading.false_affiliation_or_endorsement"],
        outcome="consent_order",
        monetary_relief="$1,000,000",
        evidence=[{
            "quote": "The CFPB found that, after the 2015 Consent Order went into effect, RMK disseminated millions of mortgage advertisements that violated the CFPB's findings in the 2015 Order and expressly prohibited by the 2015 Order.",
            "source_url": "https://files.consumerfinance.gov/f/documents/cfpb_spring-semi-annual-report_2023-11.pdf",
            "section": "CFPB Semi-Annual Report, Spring 2023",
        }],
    ),
]

FINRA = [
    entry(
        precedent_id="prec.finra.m1_finance_influencers_2024",
        source="Financial Industry Regulatory Authority (FINRA)",
        source_url="https://www.finra.org/media-center/newsreleases/2024/finra-fines-m1-finance-850000-violations-regarding-use-social-media",
        date="2024-06-12",
        title="FINRA v. M1 Finance — unsupervised social media influencer posts",
        summary="FINRA fined M1 Finance $850,000 for influencer posts that were not fair or balanced and lacked principal approval and books-and-records compliance.",
        why_this_matters="First formal FINRA discipline for firm supervision of paid social-media influencer financial promotions.",
        retrieval_keywords=["M1 Finance", "FINRA", "influencer marketing", "social media", "Rule 2210", "fair and balanced"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["finra.finance.fair_balanced", "finra.finance.no_performance_projection"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.testimonials_endorsements_disclosure"],
        outcome="fine",
        monetary_relief="$850,000",
        evidence=[{
            "quote": "M1 Finance influencers made social media posts promoting the firm that were not fair and balanced, in violation of FINRA Rules 2210 (Communications with the Public) and 2010 (Standards of Commercial Honor and Principles of Trade).",
            "source_url": "https://www.finra.org/media-center/newsreleases/2024/finra-fines-m1-finance-850000-violations-regarding-use-social-media",
            "section": "FINRA News Release, June 2024",
        }],
    ),
]

FEC = [
    entry(
        precedent_id="prec.fec.vitter_disclaimer_2009",
        source="U.S. Federal Election Commission",
        source_url="https://www.fec.gov/updates/fec-completes-action-in-12-enforcement-cases-civil-penalties-in-two-matters-total-30000/",
        date="2009-03-05",
        title="FEC MUR 5587R — David Vitter committee inadequate phone-bank disclaimers",
        summary="The David Vitter for U.S. Senate committee paid a $25,000 civil penalty for phone-bank calls that failed to clearly state the committee paid for the communication.",
        why_this_matters="Canonical paid-for-by disclaimer enforcement for telemarketing-style political outreach.",
        retrieval_keywords=["FEC", "disclaimer", "phone bank", "David Vitter", "paid for by", "MUR 5587"],
        category_ids=["political"],
        violated_clause_ids=["fec.political.disclaimer"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="civil_penalty",
        monetary_relief="$25,000",
        evidence=[{
            "quote": "The David Vitter for U.S. Senate committee agreed to pay a $25,000 civil penalty for failing to include adequate disclaimers on telephone bank calls placed before the 2004 general election.",
            "source_url": "https://www.fec.gov/updates/fec-completes-action-in-12-enforcement-cases-civil-penalties-in-two-matters-total-30000/",
            "section": "FEC Update, MUR 5587R",
        }],
    ),
    entry(
        precedent_id="prec.fec.google_text_ad_disclaimers_2010",
        source="U.S. Federal Election Commission",
        source_url="https://www.fec.gov/updates/ao-2010-19-disclaimers-on-internet-text-ads/",
        date="2010-08-05",
        title="FEC AO 2010-19 — Google text ads and political disclaimers",
        summary="The FEC concluded Google's proposed AdWords text ads for political committees, with full disclaimers on landing pages rather than in the ad unit, did not violate the Act under the described circumstances.",
        why_this_matters="Foundational platform-policy precedent for short-form political ad disclaimer placement online.",
        retrieval_keywords=["FEC", "Google AdWords", "text ads", "disclaimer", "landing page", "AO 2010-19"],
        category_ids=["political"],
        violated_clause_ids=["fec.political.disclaimer", "google.political.paid_for_by"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Candidates, their authorized committees and other political committees need not display disclaimers on text ads they sponsor that are generated through Google, Inc.'s AdWords program. The full disclaimer would instead appear on a 'landing page' that appears when a user clicks through a text ad.",
            "source_url": "https://www.fec.gov/updates/ao-2010-19-disclaimers-on-internet-text-ads/",
            "section": "FEC Advisory Opinion 2010-19",
        }],
    ),
]

STATE_AG = [
    entry(
        precedent_id="prec.nyag.juul_youth_marketing_2023",
        source="New York State Attorney General",
        source_url="https://ag.ny.gov/press-release/2023/attorney-general-james-secures-462-million-juul-its-role-youth-vaping-epidemic",
        date="2023-04-12",
        title="NY AG multistate settlement — JUUL youth-targeted marketing",
        summary="JUUL agreed to pay $462 million to six states and D.C., with New York receiving $112.7 million, for deceptive youth-oriented marketing including colorful ads and youth-appealing flavors.",
        why_this_matters="Largest multistate nicotine marketing settlement; models youth-appeal restrictions in tobacco/nicotine ads.",
        retrieval_keywords=["JUUL", "youth vaping", "nicotine marketing", "New York AG", "flavors", "e-cigarette"],
        category_ids=["drugs", "minors", "misleading"],
        violated_clause_ids=["fda.atc.tobacco_format", "meta.atc.tobacco"],
        canonical_ids=["atc.tobacco_advertising_format_restrictions", "minors.age_restricted_products_not_shown_to_minors"],
        outcome="settlement",
        monetary_relief="$462,000,000 (multistate); $112,700,000 (NY share)",
        evidence=[{
            "quote": "In November 2019, Attorney General James sued JUUL for its deceptive and misleading marketing that glamorized vaping with colorful ads featuring young models using fruity, sweet, and minty flavors that appealed to youth.",
            "source_url": "https://ag.ny.gov/press-release/2023/attorney-general-james-secures-462-million-juul-its-role-youth-vaping-epidemic",
            "section": "NY AG Press Release, April 12, 2023",
        }],
    ),
    entry(
        precedent_id="prec.nyag.draftkings_fanduel_2016",
        source="New York State Attorney General",
        source_url="https://ag.ny.gov/press-release/2016/ag-schneiderman-announces-12-million-settlement-draftkings-and-fanduel",
        date="2016-10-25",
        title="NY AG v. DraftKings and FanDuel — deceptive daily fantasy advertising",
        summary="DraftKings and FanDuel each paid $6 million to settle NY AG allegations of false advertising about odds of winning, deposit matches, and failure to disclose that top 1% of players won most prizes.",
        why_this_matters="Landmark gambling-adjacent deception case on odds disclosure and responsible gambling messaging.",
        retrieval_keywords=["DraftKings", "FanDuel", "daily fantasy", "gambling advertising", "odds disclosure", "New York AG"],
        category_ids=["gambling", "misleading", "financial"],
        violated_clause_ids=["google.gambling.responsible", "ftc.misleading.reasonable_basis"],
        canonical_ids=["gambling.responsible_gambling_required", "misleading.missing_or_inconsistent_material_info"],
        outcome="settlement",
        monetary_relief="$12,000,000 ($6M each)",
        evidence=[{
            "quote": "Each Company Agrees To Pay $6 Million For Repeated False Advertising Violations In New York; Year-Long Investigation Found That Both Companies Had Consistently Misled Consumers In Advertisements.",
            "source_url": "https://ag.ny.gov/press-release/2016/ag-schneiderman-announces-12-million-settlement-draftkings-and-fanduel",
            "section": "NY AG Press Release, Oct 25, 2016",
        }],
    ),
]

DOJ = [
    entry(
        precedent_id="prec.doj.counterfeit_phones_amazon_2023",
        source="U.S. Department of Justice",
        source_url="https://www.justice.gov/usao-id/pr/five-family-members-sentenced-prison-and-ordered-forfeit-combined-519-million-dollars",
        date="2023-03-23",
        title="DOJ — counterfeit Apple/Samsung phones sold on Amazon and eBay",
        summary="Five family members were sentenced and ordered to forfeit over $51.9 million for wire fraud and trafficking counterfeit phones misrepresented as new genuine products on Amazon.com and eBay.com.",
        why_this_matters="Criminal enforcement against counterfeit goods sold via major ecommerce ad/marketplace channels.",
        retrieval_keywords=["counterfeit", "Amazon", "eBay", "Apple", "Samsung", "trademark", "wire fraud"],
        category_ids=["ip_trademark", "misleading"],
        violated_clause_ids=["google.ip.counterfeit_goods", "meta.ip.counterfeit_goods"],
        canonical_ids=["ip.counterfeit_goods_prohibited"],
        outcome="court_order",
        monetary_relief="$51,900,000+ forfeiture",
        evidence=[{
            "quote": "They sold counterfeit cellphones and cellphone accessories on Amazon.com and eBay.com that the defendants misrepresented as new and genuine Apple and Samsung products.",
            "source_url": "https://www.justice.gov/usao-id/pr/five-family-members-sentenced-prison-and-ordered-forfeit-combined-519-million-dollars",
            "section": "DOJ USAO Idaho, March 2023",
        }],
    ),
    entry(
        precedent_id="prec.doj_hud.trident_redlining_2022",
        source="U.S. Department of Justice / Consumer Financial Protection Bureau",
        source_url="https://files.consumerfinance.gov/f/documents/cfpb_fall-2022-semi-annual-report_2023-06.pdf",
        date="2022-09-14",
        title="DOJ/CFPB v. Trident Mortgage — discriminatory lending marketing (redlining)",
        summary="Trident Mortgage agreed to a consent order requiring $18.4 million in a loan subsidy fund and a $4 million penalty for redlining and discouraging applications in majority-minority Philadelphia neighborhoods.",
        why_this_matters="Fair lending marketing precedent for discriminatory outreach and housing credit advertising.",
        retrieval_keywords=["Trident Mortgage", "redlining", "ECOA", "FHA", "discriminatory marketing", "Philadelphia"],
        category_ids=["discrimination", "financial"],
        violated_clause_ids=["hud.housing.discriminatory_ad", "ftc.credit.ecoa_discouragement"],
        canonical_ids=["discrimination.discriminatory_ad_content_prohibited", "discrimination.restricted_targeting_protected_class"],
        outcome="consent_order",
        monetary_relief="$4,000,000 penalty; $18,400,000 loan subsidy fund",
        evidence=[{
            "quote": "The CFPB's and DOJ's joint complaint alleged that Trident engaged in unlawful discrimination on the basis of race, color, or national origin against applicants and prospective applicants, including by redlining majority minority neighborhoods.",
            "source_url": "https://files.consumerfinance.gov/f/documents/cfpb_fall-2022-semi-annual-report_2023-06.pdf",
            "section": "CFPB Semi-Annual Report, Fall 2022",
        }],
    ),
]

PLATFORMS = [
    entry(
        precedent_id="prec.meta.siep_disclaimer_enforcement_2024",
        source="Meta Transparency Center",
        source_url="https://transparency.meta.com/sr/european-parliament-report-2024",
        date="2024-06-23",
        title="Meta SIEP policy — mass removal of non-compliant political ads (EU 2024)",
        summary="Meta reported removing over 130,000 social-issue/election/political ads in the EU for SIEP policy non-compliance during the 2024 European Parliament election period while labeling 400,000+ compliant ads.",
        why_this_matters="Documents platform-scale enforcement of paid-for-by and authorization requirements on political ads.",
        retrieval_keywords=["Meta", "SIEP", "political ads", "Paid for by", "Ad Library", "EU elections", "disclaimer"],
        category_ids=["political"],
        violated_clause_ids=["meta.political.authorization_disclaimer"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="suspension",
        monetary_relief=None,
        evidence=[{
            "quote": "As a result of the above policies and measures, around the EP elections, we labelled over 400,000 SIEP ads in the EU, and we removed over 130,000 SIEP ads in the EU for non-compliance with Meta's SIEP policy.",
            "source_url": "https://transparency.meta.com/sr/european-parliament-report-2024",
            "section": "Meta EP Post-Elections Report 2024",
        }],
    ),
    entry(
        precedent_id="prec.google.election_ads_disclosure_2024",
        source="Google Ads Policy",
        source_url="https://support.google.com/adspolicy/answer/6014595?hl=en",
        date="2024-01-01",
        title="Google election ads — mandatory Paid for by disclosure and verification",
        summary="Google requires verified election advertisers in covered regions to include a Paid for by disclosure, auto-generated for most formats, with advertiser verification and transparency reporting.",
        why_this_matters="Primary platform rule cited when rejecting or verifying U.S. election and issue ads lacking disclaimers.",
        retrieval_keywords=["Google Ads", "election ads", "Paid for by", "verification", "political content", "disclosure"],
        category_ids=["political"],
        violated_clause_ids=["google.political.paid_for_by", "google.political.compliance_verification"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "All election ads run by verified election advertisers in regions where election ads verification is required must contain a disclosure that identifies who paid for the ad.",
            "source_url": "https://support.google.com/adspolicy/answer/6014595?hl=en",
            "section": "Google Ads Policy — Political content",
        }],
    ),
]

TTB = [
    entry(
        precedent_id="prec.ttb.mckenzie_energy_alcohol_2007",
        source="Alcohol and Tobacco Tax and Trade Bureau (TTB)",
        source_url="https://www.ttb.gov/media/70996/download?inline=",
        date="2007-07-16",
        title="TTB v. McKenzie River — misleading energy/stimulating alcohol ads",
        summary="McKenzie River Corporation served a 7-day basic permit suspension and paid a $200,000 offer in compromise after TTB found print ads implying its alcohol beverages had stimulating or energizing effects.",
        why_this_matters="TTB enforcement template for prohibited health/energy claims in alcohol advertising.",
        retrieval_keywords=["TTB", "alcohol advertising", "energy claims", "misleading health", "McKenzie River", "Sparks"],
        category_ids=["alcohol", "health", "misleading"],
        violated_clause_ids=["ttb.atc.alcohol_statements"],
        canonical_ids=["atc.alcohol_mandatory_and_prohibited_statements"],
        outcome="consent_order",
        monetary_relief="$200,000 offer in compromise; 7-day permit suspension",
        evidence=[{
            "quote": "A TTB investigation revealed that McKenzie River Corporation had published print advertisements implying that its alcohol beverage product had a stimulating or an energizing effect on the consumer.",
            "source_url": "https://www.ttb.gov/media/70996/download?inline=",
            "section": "TTB Industry Circular (McKenzie enforcement)",
        }],
    ),
]

FDA_EXPANSION = [
    entry(
        precedent_id="prec.fda.puff_bar_warning_2020",
        source="U.S. Food and Drug Administration",
        source_url="https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/cool-clouds-distribution-inc-dba-puff-bar-608526-07202020",
        date="2020-07-20",
        title="FDA warning — Puff Bar unauthorized ENDS marketing",
        summary="FDA warned Cool Clouds Distribution (Puff Bar) that flavored disposable ENDS products on puffbar.com were new tobacco products sold without required marketing authorization.",
        why_this_matters="Early FDA enforcement anchor for youth-appealing disposable nicotine products promoted online.",
        retrieval_keywords=["Puff Bar", "FDA warning letter", "ENDS", "youth vaping", "unauthorized tobacco", "flavors"],
        category_ids=["drugs", "minors"],
        violated_clause_ids=["fda.atc.tobacco_format"],
        canonical_ids=["atc.tobacco_advertising_format_restrictions", "atc.tobacco_and_nicotine_ads_prohibited"],
        outcome="warning_letter",
        monetary_relief=None,
        evidence=[{
            "quote": "These products do not have FDA marketing authorization orders in effect under section 910(c)(1)(A)(i) of the FD&C Act and are not otherwise exempt from the marketing authorization requirement.",
            "source_url": "https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/warning-letters/cool-clouds-distribution-inc-dba-puff-bar-608526-07202020",
            "section": "FDA Warning Letter 608526",
        }],
    ),
    entry(
        precedent_id="prec.fda.puff_bar_retailer_blitz_2022",
        source="U.S. Food and Drug Administration",
        source_url="https://www.fda.gov/news-events/press-announcements/fda-conducts-retailer-inspection-blitz-cracks-down-illegal-sales-popular-disposable-e-cigarettes",
        date="2022-10-12",
        title="FDA retailer blitz — illegal Puff/Hyde disposable e-cigarette sales",
        summary="FDA issued warning letters to 30 retailers and one distributor for illegally selling unauthorized Puff and Hyde disposable e-cigarettes, among the most popular brands with youth in 2022 NYTS data.",
        why_this_matters="Supply-chain enforcement tying youth-popular brands to illegal retail promotion channels.",
        retrieval_keywords=["Puff Bar", "Hyde", "FDA retailer blitz", "youth e-cigarettes", "disposable vapes", "warning letters"],
        category_ids=["drugs", "minors"],
        violated_clause_ids=["fda.atc.tobacco_format", "tiktok.atc.tobacco"],
        canonical_ids=["atc.tobacco_and_nicotine_ads_prohibited", "minors.age_restricted_products_not_shown_to_minors"],
        outcome="warning_letter",
        monetary_relief=None,
        evidence=[{
            "quote": "The unauthorized products were various types of Puff and Hyde brand disposable e-cigarettes, which were two of the most commonly reported brands used by youth e-cigarette users in 2022.",
            "source_url": "https://www.fda.gov/news-events/press-announcements/fda-conducts-retailer-inspection-blitz-cracks-down-illegal-sales-popular-disposable-e-cigarettes",
            "section": "FDA Press Announcement, Oct 12, 2022",
        }],
    ),
]

EXTRA = [
    entry(
        precedent_id="prec.ftc.nextmed_weight_loss_2025",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2025/07/ftc-takes-action-against-telemedicine-firm-nextmed-over-charges-it-used-misleading-prices-fake",
        date="2025-07-14",
        title="FTC v. NextMed — deceptive GLP-1 weight-loss program advertising",
        summary="NextMed agreed to pay $150,000 to settle FTC charges that it used deceptive pricing, unsubstantiated weight-loss claims, fake reviews, and hidden drug costs to sell telehealth GLP-1 programs.",
        why_this_matters="Telehealth weight-loss ad precedent combining before/after claims, hidden fees, and fake social proof.",
        retrieval_keywords=["NextMed", "GLP-1", "Wegovy", "Ozempic", "weight loss ads", "fake reviews", "telehealth"],
        category_ids=["health", "misleading"],
        violated_clause_ids=["ftc.health.truthful_substantiated", "ftc.misleading.reasonable_basis"],
        canonical_ids=["health.unsubstantiated_health_claims", "misleading.before_after_distortion"],
        outcome="settlement",
        monetary_relief="$150,000",
        evidence=[{
            "quote": "NextMed sold its membership programs at an advertised monthly price, typically at $138 or $188, without adequately disclosing that the price did not include the cost of the actual GLP-1 drug.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2025/07/ftc-takes-action-against-telemedicine-firm-nextmed-over-charges-it-used-misleading-prices-fake",
            "section": "FTC Press Release, July 14, 2025",
        }],
    ),
    entry(
        precedent_id="prec.hud.facebook_housing_ads_2019",
        source="U.S. Department of Housing and Urban Development",
        source_url="https://archives.hud.gov/news/2019/pr19-035.cfm",
        date="2019-03-28",
        title="HUD charge — Facebook housing ad discrimination (supplement to DOJ settlement)",
        summary="HUD charged Facebook with violating the Fair Housing Act by enabling advertisers to exclude audiences by race, religion, familial status, and other protected classes in housing ads.",
        why_this_matters="Foundational FHA charge on targeted housing advertising that preceded the DOJ/HUD Meta settlement already in corpus.",
        retrieval_keywords=["HUD", "Facebook", "Fair Housing Act", "housing ads", "discrimination", "ad targeting"],
        category_ids=["discrimination"],
        violated_clause_ids=["hud.housing.discriminatory_ad"],
        canonical_ids=["discrimination.discriminatory_ad_content_prohibited", "discrimination.restricted_targeting_protected_class"],
        outcome="court_order",
        monetary_relief=None,
        evidence=[{
            "quote": "HUD is charging Facebook with violating the Fair Housing Act by encouraging, enabling, and causing housing discrimination through the company's advertising platform.",
            "source_url": "https://archives.hud.gov/news/2019/pr19-035.cfm",
            "section": "HUD Press Release pr19-035, March 28, 2019",
        }],
    ),
    entry(
        precedent_id="prec.fec.healthcare_leadgen_warning_2024",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2024/12/ftc-staff-sends-warning-letters-healthcare-plan-marketers-lead-generators",
        date="2024-12-03",
        title="FTC staff warning letters — healthcare plan marketers and lead generators",
        summary="FTC staff sent warning letters to 21 healthcare plan marketers and lead generators about deceptive ACA and comprehensive-coverage claims during open enrollment.",
        why_this_matters="Official staff guidance citing prior lead-gen enforcement; useful for political-adjacent health plan ad compliance patterns.",
        retrieval_keywords=["FTC warning letter", "health insurance leads", "ACA", "open enrollment", "lead generators", "deceptive health plans"],
        category_ids=["health", "financial", "misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "ftc.misleading.express_implied"],
        canonical_ids=["misleading.unsubstantiated_objective_claims", "finance.misleading_or_unbalanced_claims"],
        outcome="warning_letter",
        monetary_relief=None,
        evidence=[{
            "quote": "Based on information collected by FTC staff and the agency's enforcement experience in this area, the types of claims FTC staff warns the companies about include those that may misrepresent the benefits included in a healthcare plan, including any insurance benefits.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2024/12/ftc-staff-sends-warning-letters-healthcare-plan-marketers-lead-generators",
            "section": "FTC Press Release, Dec 3, 2024",
        }],
    ),
]


def verify_clauses(precedents: list[dict]) -> None:
    import yaml
    clause_ids = set()
    for path in (ROOT / "corpus").glob("*.yaml"):
        doc = yaml.safe_load(path.read_text()) or {}
        for c in doc.get("clauses", []) or []:
            clause_ids.add(c["id"])
    for p in precedents:
        for cid in p.get("violated_clause_ids", []) or []:
            if cid not in clause_ids:
                raise SystemExit(f"Unknown clause {cid} in {p['precedent_id']}")


def main() -> None:
    all_new = (
        FTC_EXPANSION
        + SEC_EXPANSION
        + CFPB
        + FINRA
        + FEC
        + STATE_AG
        + DOJ
        + PLATFORMS
        + TTB
        + FDA_EXPANSION
        + EXTRA
    )
    verify_clauses(all_new)
    print(f"Generating {len(all_new)} new precedents")

    dump_file(
        PREC / "ftc_expansion.yaml",
        "# FTC enforcement precedents — Phase 1 expansion (official sources only).",
        FTC_EXPANSION + [EXTRA[0], EXTRA[2]],
    )
    dump_file(
        PREC / "sec_expansion.yaml",
        "# SEC enforcement precedents — Phase 1 expansion.",
        SEC_EXPANSION,
    )
    dump_file(PREC / "cfpb.yaml", "# CFPB enforcement precedents.", CFPB)
    dump_file(PREC / "finra.yaml", "# FINRA enforcement precedents.", FINRA)
    dump_file(PREC / "fec.yaml", "# FEC political advertising precedents.", FEC)
    dump_file(PREC / "state_ag.yaml", "# State Attorney General enforcement precedents.", STATE_AG)
    dump_file(PREC / "doj.yaml", "# DOJ enforcement precedents (non-HUD seed cases).", DOJ)
    dump_file(PREC / "platforms.yaml", "# Platform policy enforcement precedents (official transparency/policy pages).", PLATFORMS)
    dump_file(PREC / "ttb.yaml", "# TTB alcohol advertising enforcement.", TTB)
    dump_file(PREC / "fda_expansion.yaml", "# FDA tobacco/ENDS enforcement — Phase 1 expansion.", FDA_EXPANSION)
    dump_file(PREC / "hud_expansion.yaml", "# HUD fair housing advertising enforcement.", [EXTRA[1]])


if __name__ == "__main__":
    main()
