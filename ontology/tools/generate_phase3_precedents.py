#!/usr/bin/env python3
"""Generate Phase 3 precedent YAML sidecars (35 verified entries — final US expansion)."""
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
                lines.append(f'        section: "{ev["section"]}"')
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n")


FTC_PHASE3 = [
    entry(
        precedent_id="prec.ftc.hrblock_free_filing_2024",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2024/11/ftc-action-stops-hr-blocks-unfair-downgrading-practices-deceptive-promises-free-filing",
        date="2024-11-21",
        title="FTC v. H&R Block — deceptive 'free' filing and unfair downgrading",
        summary="H&R Block agreed to pay $7 million and stop unfair downgrading practices and deceptive 'free' tax filing claims after the FTC sued over dark-pattern downgrade flows and data deletion.",
        why_this_matters="Follow-on to Intuit/TurboTax 'free filing' deception — tax-prep ads with hidden eligibility and downgrade friction.",
        retrieval_keywords=["H&R Block", "free filing", "tax prep", "downgrade", "dark patterns", "TurboTax", "$7 million"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "cfpb.finance.actually_available_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "misleading.unsubstantiated_objective_claims"],
        outcome="settlement",
        monetary_relief="$7,000,000",
        evidence=[{
            "quote": "A proposed FTC settlement would stop H&R Block from unfairly requiring consumers seeking to downgrade to a cheaper H&R Block product to contact customer service, from unfairly deleting users' previously entered data and from making deceptive claims about \"free\" tax filing.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2024/11/ftc-action-stops-hr-blocks-unfair-downgrading-practices-deceptive-promises-free-filing",
            "section": "FTC Press Release, November 2024",
        }],
    ),
    entry(
        precedent_id="prec.ftc.instacart_deceptive_2025",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2025/12/instacart-pay-60-million-consumer-refunds-settle-ftc-lawsuit-over-allegations-it-engaged-deceptive",
        date="2025-12-18",
        title="FTC v. Instacart — deceptive delivery fees and subscription enrollment",
        summary="Instacart agreed to pay $60 million in consumer refunds to settle FTC charges of false 'free delivery' ads, hidden satisfaction-guarantee refund options, and Instacart+ enrollments without express informed consent.",
        why_this_matters="Major grocery-delivery case on subscription dark patterns, hidden fees, and satisfaction-guarantee ad claims.",
        retrieval_keywords=["Instacart", "free delivery", "Instacart+", "subscription", "ROSCA", "dark patterns", "$60 million"],
        category_ids=["misleading", "financial"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "google.misrep.dishonest_pricing"],
        canonical_ids=["misleading.missing_or_inconsistent_material_info", "misleading.unsubstantiated_objective_claims"],
        outcome="settlement",
        monetary_relief="$60,000,000",
        evidence=[{
            "quote": "Today, the Federal Trade Commission announced that grocery delivery provider Instacart will pay $60 million in refunds to consumers to settle allegations that the company engaged in numerous unlawful tactics that harmed shoppers and raised the cost of grocery shopping for Americans.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2025/12/instacart-pay-60-million-consumer-refunds-settle-ftc-lawsuit-over-allegations-it-engaged-deceptive",
            "section": "FTC Press Release, December 18, 2025",
        }],
    ),
    entry(
        precedent_id="prec.ftc.opendoor_ibuying_2022",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2022/08/ftc-takes-action-stop-online-home-buying-firm-opendoor-labs-inc-cheating-potential-sellers",
        date="2022-08-01",
        title="FTC v. Opendoor — deceptive iBuyer savings claims",
        summary="Opendoor agreed to pay $62 million after the FTC found it misled home sellers with charts falsely showing they would net more money selling to Opendoor than on the open market.",
        why_this_matters="Landmark real-estate iBuyer ad case on unsubstantiated savings comparisons and net-proceeds charts.",
        retrieval_keywords=["Opendoor", "iBuyer", "home sellers", "deceptive marketing", "net proceeds", "$62 million"],
        category_ids=["misleading", "financial"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "google.misrep.unreliable_claims"],
        canonical_ids=["misleading.unsubstantiated_objective_claims", "finance.misleading_or_unbalanced_claims"],
        outcome="consent_order",
        monetary_relief="$62,000,000",
        evidence=[{
            "quote": "The FTC alleged that Opendoor pitched potential sellers using misleading and deceptive information, and in reality, most people who sold to Opendoor made thousands of dollars less than they would have made selling their homes using the traditional process.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2022/08/ftc-takes-action-stop-online-home-buying-firm-opendoor-labs-inc-cheating-potential-sellers",
            "section": "FTC Press Release, August 1, 2022",
        }],
    ),
    entry(
        precedent_id="prec.ftc.fake_reviews_rule_2024",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/system/files/ftc_gov/pdf/r311003consumerreviewstestimonialsfinalrulefrn.pdf",
        date="2024-08-14",
        title="FTC Final Rule on Consumer Reviews and Testimonials",
        summary="The FTC issued a final rule prohibiting fake reviews, insider testimonials without disclosure, review suppression, and sale of fake social-media influence indicators, with civil penalty authority for knowing violations.",
        why_this_matters="Foundational 2024 rule for fake reviews, astroturfing, and influencer metrics fraud in ads and listings.",
        retrieval_keywords=["fake reviews", "testimonials rule", "FTC Part 465", "review suppression", "social media influence", "2024 rule"],
        category_ids=["misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "google.misrep.unreliable_claims"],
        canonical_ids=["misleading.unsubstantiated_objective_claims", "misleading.false_affiliation_or_endorsement"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "This final rule, among other things, prohibits selling or purchasing fake consumer reviews or testimonials, buying positive or negative consumer reviews, certain insiders creating consumer reviews or testimonials without clearly disclosing their relationships, creating a company-controlled review website that falsely purports to provide independent reviews, certain review suppression practices, and selling or purchasing fake indicators of social media influence.",
            "source_url": "https://www.ftc.gov/system/files/ftc_gov/pdf/r311003consumerreviewstestimonialsfinalrulefrn.pdf",
            "section": "16 CFR Part 465 Final Rule SUMMARY",
        }],
    ),
    entry(
        precedent_id="prec.ftc.vonage_dark_patterns_2022",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2022/11/ftc-action-against-vonage-results-100-million-customers-trapped-illegal-dark-patterns-junk-fees-when-trying-cancel-service",
        date="2022-11-03",
        title="FTC v. Vonage — dark-pattern cancellation and junk fees",
        summary="Vonage agreed to pay $100 million in refunds after the FTC charged it used dark patterns to trap customers in subscriptions and charged unexpected early-termination fees when they tried to cancel.",
        why_this_matters="Canonical dark-pattern and junk-fee precedent for negative-option and subscription ads.",
        retrieval_keywords=["Vonage", "dark patterns", "cancellation", "junk fees", "subscription trap", "$100 million"],
        category_ids=["misleading", "financial"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "cfpb.finance.actually_available_terms"],
        canonical_ids=["misleading.missing_or_inconsistent_material_info"],
        outcome="settlement",
        monetary_relief="$100,000,000",
        evidence=[{
            "quote": "The FTC alleges that the company used dark patterns to make it difficult for consumers to cancel and often continued to illegally charge them even after they spoke to an agent directly and requested cancellation.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2022/11/ftc-action-against-vonage-results-100-million-customers-trapped-illegal-dark-patterns-junk-fees-when-trying-cancel-service",
            "section": "FTC Press Release, November 3, 2022",
        }],
    ),
    entry(
        precedent_id="prec.ftc.rite_aid_facial_recognition_2023",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2023/12/rite-aid-banned-using-ai-facial-recognition-after-ftc-says-retailer-deployed-technology-without",
        date="2023-12-19",
        title="FTC v. Rite Aid — AI facial recognition without safeguards",
        summary="Rite Aid agreed to a five-year ban on using facial recognition for surveillance after the FTC found it falsely flagged customers, especially women and people of color, as shoplifters without reasonable procedures.",
        why_this_matters="First major FTC biometric/AI surveillance order — relevant to automated ad targeting and sensitive-attribute harm.",
        retrieval_keywords=["Rite Aid", "facial recognition", "AI", "biometrics", "retail surveillance", "discrimination"],
        category_ids=["privacy", "discrimination", "misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "google.privacy.sensitive_interest_categories"],
        canonical_ids=["privacy.sensitive_attribute_targeting_prohibited", "discrimination.discriminatory_ad_content_prohibited"],
        outcome="consent_order",
        monetary_relief=None,
        evidence=[{
            "quote": "Rite Aid will be prohibited from using facial recognition technology for surveillance purposes for five years to settle Federal Trade Commission charges that the retailer failed to implement reasonable procedures and prevent harm to consumers in its use of facial recognition technology in hundreds of stores.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2023/12/rite-aid-banned-using-ai-facial-recognition-after-ftc-says-retailer-deployed-technology-without",
            "section": "FTC Press Release, December 19, 2023",
        }],
    ),
    entry(
        precedent_id="prec.ftc.publishers_clearing_house_2023",
        source="U.S. Federal Trade Commission",
        source_url="https://www.ftc.gov/news-events/news/press-releases/2023/06/ftc-takes-action-against-publishers-clearing-house-misleading-consumers-about-sweepstakes-entries",
        date="2023-06-26",
        title="FTC v. Publishers Clearing House — sweepstakes dark patterns",
        summary="Publishers Clearing House agreed to pay $18.5 million and overhaul its online sweepstakes and sales flows after the FTC charged dark-pattern deception that a purchase was required or improved odds of winning.",
        why_this_matters="Sweepstakes and lead-gen ad precedent on purchase-to-enter deception and surprise fees targeting older consumers.",
        retrieval_keywords=["Publishers Clearing House", "PCH", "sweepstakes", "dark patterns", "purchase to enter", "$18.5 million"],
        category_ids=["misleading", "gambling"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "google.misrep.misleading_ad_design"],
        canonical_ids=["misleading.missing_or_inconsistent_material_info", "gambling.realmoney_requires_license_and_authorization"],
        outcome="settlement",
        monetary_relief="$18,500,000",
        evidence=[{
            "quote": "In a complaint against PCH, the FTC charges that the company uses \"dark patterns\" to mislead consumers about how to enter the company's well-known sweepstakes drawings and made them believe that a purchase is necessary to win or would increase their chances of winning, and that their sweepstakes entries are incomplete even when they are not.",
            "source_url": "https://www.ftc.gov/news-events/news/press-releases/2023/06/ftc-takes-action-against-publishers-clearing-house-misleading-consumers-about-sweepstakes-entries",
            "section": "FTC Press Release, June 26, 2023",
        }],
    ),
]

SEC_PHASE3 = [
    entry(
        precedent_id="prec.sec.terraform_luna_2024",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/newsroom/press-releases/2024-73",
        date="2024-06-12",
        title="SEC v. Terraform Labs — $4.5B fraud verdict on LUNA/UST crypto securities",
        summary="Terraform Labs and Do Kwon agreed to pay more than $4.5 billion after a jury found them liable for securities fraud involving unregistered crypto asset securities that wiped out roughly $40 billion in market value.",
        why_this_matters="Landmark algorithmic stablecoin and crypto securities fraud case with jury verdict and bankruptcy distribution to harmed investors.",
        retrieval_keywords=["Terraform", "LUNA", "UST", "Do Kwon", "algorithmic stablecoin", "crypto fraud", "$4.5 billion"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["sec.finance.untrue_or_unbalanced", "google.finance.crypto"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.crypto_restricted"],
        outcome="settlement",
        monetary_relief="$4,473,828,306",
        evidence=[{
            "quote": "Terraform Labs PTE, Ltd. and Do Kwon agreed to pay more than $4.5 billion following a unanimous jury verdict holding them liable for orchestrating a years-long fraud involving crypto asset securities that led to massive investor losses when the scheme unraveled.",
            "source_url": "https://www.sec.gov/newsroom/press-releases/2024-73",
            "section": "SEC Press Release 2024-73",
        }],
    ),
    entry(
        precedent_id="prec.sec.kraken_staking_2023",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/files/litigation/complaints/2023/comp-pr2023-25.pdf",
        date="2023-02-09",
        title="SEC v. Kraken — unregistered crypto staking-as-a-service",
        summary="Kraken agreed to pay $30 million and cease its U.S. staking program after the SEC charged it with offering and selling an unregistered investment contract through pooled crypto staking services.",
        why_this_matters="Defines staking-as-a-service as securities offering — core crypto yield/advertising compliance precedent.",
        retrieval_keywords=["Kraken", "staking", "crypto yield", "unregistered securities", "proof of stake", "$30 million"],
        category_ids=["financial"],
        violated_clause_ids=["sec.finance.untrue_or_unbalanced", "google.finance.crypto"],
        canonical_ids=["finance.crypto_restricted", "finance.misleading_or_unbalanced_claims"],
        outcome="settlement",
        monetary_relief="$30,000,000",
        evidence=[{
            "quote": "This case concerns the illegal unregistered offer and sale of securities involving the staking of crypto assets.",
            "source_url": "https://www.sec.gov/files/litigation/complaints/2023/comp-pr2023-25.pdf",
            "section": "SEC Complaint, Case 3:23-cv-00588, SUMMARY ¶1",
        }],
    ),
    entry(
        precedent_id="prec.sec.impact_theory_nfts_2023",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/files/litigation/admin/2023/33-11226.pdf",
        date="2023-08-28",
        title="SEC v. Impact Theory — unregistered NFT securities offering",
        summary="Impact Theory agreed to a cease-and-desist order after the SEC found it raised about $29.9 million selling Founder's Keys NFTs as unregistered investment contracts with profit expectations tied to the company's efforts.",
        why_this_matters="First major SEC NFT-as-securities case — applies to crypto/NFT project marketing and influencer promotions.",
        retrieval_keywords=["Impact Theory", "NFT", "Founder's Keys", "unregistered offering", "Howey", "crypto art"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["sec.finance.untrue_or_unbalanced", "google.finance.crypto"],
        canonical_ids=["finance.crypto_restricted", "misleading.unsubstantiated_objective_claims"],
        outcome="consent_order",
        monetary_relief=None,
        evidence=[{
            "quote": "From October 13, 2021, to December 6, 2021, Impact Theory, a media and entertainment company, offered and sold crypto asset securities known as Founder's Keys in the form of purported non-fungible tokens, raising approximately $29.9 million worth of ether from at least hundreds of investors, including investors across the United States.",
            "source_url": "https://www.sec.gov/files/litigation/admin/2023/33-11226.pdf",
            "section": "SEC Admin Proceeding 33-11226",
        }],
    ),
    entry(
        precedent_id="prec.sec.stoner_cats_nfts_2023",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/files/litigation/admin/2023/33-11233.pdf",
        date="2023-09-13",
        title="SEC v. Stoner Cats — unregistered NFT securities offering",
        summary="Stoner Cats 2 LLC agreed to a cease-and-desist order after the SEC found it sold 10,320 NFTs for about $8.2 million in an unregistered securities offering with reasonable profit expectations from the issuer's efforts.",
        why_this_matters="Companion NFT enforcement to Impact Theory — secondary-market profit expectations and issuer promotion.",
        retrieval_keywords=["Stoner Cats", "NFT", "unregistered securities", "Ethereum", "crypto collectibles", "Howey"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["sec.finance.untrue_or_unbalanced", "google.finance.crypto"],
        canonical_ids=["finance.crypto_restricted"],
        outcome="consent_order",
        monetary_relief=None,
        evidence=[{
            "quote": "On July 27, 2021, Stoner Cats 2, LLC (\"SC2\") conducted an unregistered offering of crypto asset securities in the form of non-fungible tokens called Stoner Cats (hereinafter \"Stoner Cats NFTs\" or \"NFTs\"). SC2 offered and sold to the public, including U.S. investors, 10,320 NFTs for 0.35 ETH (approximately $800) each.",
            "source_url": "https://www.sec.gov/files/litigation/admin/2023/33-11233.pdf",
            "section": "SEC Admin Proceeding 33-11233, ¶1",
        }],
    ),
    entry(
        precedent_id="prec.sec.flyfish_club_nfts_2024",
        source="U.S. Securities and Exchange Commission",
        source_url="https://www.sec.gov/files/litigation/admin/2024/33-11305.pdf",
        date="2024-09-16",
        title="SEC v. Flyfish Club — unregistered membership NFT offering",
        summary="Flyfish Club LLC agreed to a cease-and-desist order after the SEC found it sold restaurant-membership NFTs as unregistered securities by promising token holders access and resale value tied to the issuer's restaurant development.",
        why_this_matters="Extends NFT securities theory to membership/utility tokens with marketed investment upside.",
        retrieval_keywords=["Flyfish Club", "NFT", "restaurant membership", "unregistered securities", "Gary Vaynerchuk", "VCR Group"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["sec.finance.untrue_or_unbalanced", "google.finance.crypto"],
        canonical_ids=["finance.crypto_restricted", "finance.misleading_or_unbalanced_claims"],
        outcome="consent_order",
        monetary_relief="$750,000",
        evidence=[{
            "quote": "Flyfish told investors they could potentially profit from reselling their NFTs at appreciated prices in the secondary market.",
            "source_url": "https://www.sec.gov/files/litigation/admin/2024/33-11305.pdf",
            "section": "SEC Admin Proceeding 33-11305, ¶3",
        }],
    ),
]

FINRA_PHASE3 = [
    entry(
        precedent_id="prec.finra.tradezero_influencers_2024",
        source="Financial Industry Regulatory Authority",
        source_url="https://www.finra.org/sites/default/files/2024-08/Disciplinary_Actions_August_2024.pdf",
        date="2024-06-10",
        title="FINRA v. TradeZero America — unsupervised finfluencer program",
        summary="TradeZero America was censured and fined $250,000 after FINRA found influencer posts were not fair and balanced, contained promissory claims, failed to disclose fees, and lacked principal review and recordkeeping.",
        why_this_matters="Second major finfluencer AWC after M1 — promissory 'free trading' claims without fee disclosure.",
        retrieval_keywords=["TradeZero", "finfluencer", "FINRA 2210", "influencer", "free trading platform", "$250000"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["finra.finance.fair_balanced", "sec.finance.testimonials"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.testimonials_endorsements_disclosure"],
        outcome="fine",
        monetary_relief="$250,000",
        evidence=[{
            "quote": "Without admitting or denying the findings, the firm consented to the sanctions and to the entry of findings that its influencer communications were not fair and balanced and included exaggerated and promissory statements.",
            "source_url": "https://www.finra.org/sites/default/files/2024-08/Disciplinary_Actions_August_2024.pdf",
            "section": "FINRA Disciplinary Actions August 2024, TradeZero America",
        }],
    ),
    entry(
        precedent_id="prec.finra.moomoo_influencers_2024",
        source="Financial Industry Regulatory Authority",
        source_url="https://files.brokercheck.finra.org/firm/firm_283078.pdf",
        date="2024-11-26",
        title="FINRA v. Moomoo Financial — finfluencer supervision failures",
        summary="Moomoo Financial was censured and fined $750,000 after FINRA found more than 29,000 accounts opened via influencers whose posts included promissory zero-commission claims without fee disclosure and failed to identify paid ads.",
        why_this_matters="Large-scale finfluencer referral program with misleading commission-free claims and missing ad identification.",
        retrieval_keywords=["Moomoo", "finfluencer", "zero commission", "referral links", "FINRA 2210", "$750000"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["finra.finance.fair_balanced", "sec.finance.testimonials"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.testimonials_endorsements_disclosure"],
        outcome="fine",
        monetary_relief="$750,000",
        evidence=[{
            "quote": "The firm's influencers also posted communications that claimed that the firm charged zero commission but did not disclose that other fees may apply or provide a prominent link to the firm's fee schedule.",
            "source_url": "https://files.brokercheck.finra.org/firm/firm_283078.pdf",
            "section": "FINRA BrokerCheck, Moomoo Financial AWC",
        }],
    ),
    entry(
        precedent_id="prec.finra.webull_influencers_2025",
        source="Financial Industry Regulatory Authority",
        source_url="https://www.finra.org/sites/default/files/2025-07/disciplinary-actions-july-2025.pdf",
        date="2025-05-08",
        title="FINRA v. Webull Financial — unsupervised influencer communications",
        summary="Webull Financial was censured and fined $1.6 million after FINRA found it failed to reasonably supervise or retain influencer social media posts that were not fair and balanced and included exaggerated and promissory statements.",
        why_this_matters="Largest finfluencer fine to date — scale supervision failure across hundreds of paid influencers.",
        retrieval_keywords=["Webull", "finfluencer", "social media", "FINRA 2210", "promissory statements", "$1.6 million"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["finra.finance.fair_balanced", "sec.finance.testimonials"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.testimonials_endorsements_disclosure"],
        outcome="fine",
        monetary_relief="$1,600,000",
        evidence=[{
            "quote": "Without admitting or denying the findings, the firm consented to the sanctions and to the entry of findings that it failed to reasonably supervise or retain social media communications promoting the firm.",
            "source_url": "https://www.finra.org/sites/default/files/2025-07/disciplinary-actions-july-2025.pdf",
            "section": "FINRA Disciplinary Actions July 2025, Webull Financial",
        }],
    ),
]

CFPB_PHASE3 = [
    entry(
        precedent_id="prec.cfpb.hello_digit_2022",
        source="Consumer Financial Protection Bureau",
        source_url="https://www.consumerfinance.gov/about-us/newsroom/cfpb-takes-action-against-hello-digit-for-lying-to-consumers-about-its-automated-savings-algorithm/",
        date="2022-08-10",
        title="CFPB v. Hello Digit — deceptive automated savings algorithm",
        summary="Hello Digit paid a $2.7 million penalty after the CFPB found it falsely guaranteed no overdrafts, failed to reimburse fees, and kept interest that it said would go to consumers.",
        why_this_matters="Fintech savings-app marketing precedent on algorithm performance claims and fee reimbursement promises.",
        retrieval_keywords=["Hello Digit", "automated savings", "overdraft", "fintech", "deceptive algorithm", "$2.7 million"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["cfpb.finance.actually_available_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims"],
        outcome="consent_order",
        monetary_relief="$2,700,000",
        evidence=[{
            "quote": "Hello Digit was meant to save people money, but instead the company falsely guaranteed no overdrafts with its product, broke its promises to make amends on its mistakes, and pocketed a portion of the interest that should have gone to consumers.",
            "source_url": "https://www.consumerfinance.gov/about-us/newsroom/cfpb-takes-action-against-hello-digit-for-lying-to-consumers-about-its-automated-savings-algorithm/",
            "section": "CFPB Press Release, August 10, 2022",
        }],
    ),
    entry(
        precedent_id="prec.cfpb.onemain_addons_2023",
        source="Consumer Financial Protection Bureau",
        source_url="https://www.consumerfinance.gov/enforcement/actions/onemain-financial-holdings-llc-et-al/",
        date="2023-05-15",
        title="CFPB v. OneMain — deceptive optional add-on products",
        summary="OneMain agreed to pay $20 million after the CFPB found it deceptively sold and financed optional credit-insurance and non-credit add-ons and failed to refund interest on cancelled products.",
        why_this_matters="Installment-lender add-on marketing precedent for hidden costs and refund deception in loan ads.",
        retrieval_keywords=["OneMain", "add-on products", "credit insurance", "deceptive sales", "installment loans", "$20 million"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["cfpb.finance.actually_available_terms", "cfpb.finance.trigger_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.credit_advertising_trigger_terms"],
        outcome="consent_order",
        monetary_relief="$20,000,000",
        evidence=[{
            "quote": "The Consumer Financial Protection Bureau (Bureau) has reviewed the practices of OneMain Financial Holdings, LLC relating to the marketing, sales, and financing of optional ancillary products (Optional Add-On Products) and has identified unfair, deceptive, and abusive acts or practices engaged in by Respondent in violation of Sections 1031 and 1036 of the CFPA.",
            "source_url": "https://files.consumerfinance.gov/f/documents/cfpb_onemain-financial-holdings-llc_consent-order_2023-05.pdf",
            "section": "CFPB Consent Order 2023-CFPB-0003, Background",
        }],
    ),
    entry(
        precedent_id="prec.cfpb.sendwave_remit_2023",
        source="Consumer Financial Protection Bureau",
        source_url="https://www.consumerfinance.gov/enforcement/actions/chime-inc-dba-sendwave/",
        date="2023-10-17",
        title="CFPB v. Sendwave — deceptive remittance transfer advertising",
        summary="Sendwave paid $1.5 million in redress and a $1.5 million penalty after the CFPB found it misrepresented transfer speed and cost and violated Remittance Transfer Rule disclosure requirements.",
        why_this_matters="Money-transfer app ad precedent on speed/cost misrepresentation and required fee disclosures.",
        retrieval_keywords=["Sendwave", "Chime", "remittance", "money transfer", "deceptive fees", "Reg E"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["cfpb.finance.actually_available_terms", "cfpb.finance.trigger_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "misleading.missing_or_inconsistent_material_info"],
        outcome="consent_order",
        monetary_relief="$3,000,000 (redress + penalty)",
        evidence=[{
            "quote": "The Bureau found that Sendwave violated the Consumer Financial Protection Act of 2010's (CFPA) prohibition on deceptive acts and practices by misrepresenting to consumers the speed and cost of its remittance transfers.",
            "source_url": "https://www.consumerfinance.gov/enforcement/actions/chime-inc-dba-sendwave/",
            "section": "CFPB Enforcement Action Summary",
        }],
    ),
    entry(
        precedent_id="prec.cfpb.bloomtech_isa_2024",
        source="Consumer Financial Protection Bureau",
        source_url="https://files.consumerfinance.gov/f/documents/cfpb_bloomtech-inc-consent-order_2024-04.pdf",
        date="2024-04-15",
        title="CFPB v. BloomTech — deceptive income-share agreement lending",
        summary="BloomTech (Lambda School) was ordered to stop deceptive ISA practices and pay penalties after the CFPB found it misled students about job-placement rates and failed to disclose ISA finance charges under TILA.",
        why_this_matters="Ed-tech and coding-bootcamp ad precedent on job-outcome claims and ISA credit advertising.",
        retrieval_keywords=["BloomTech", "Lambda School", "income share agreement", "ISA", "coding bootcamp", "job placement"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["cfpb.finance.actually_available_terms", "cfpb.finance.trigger_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.credit_advertising_trigger_terms"],
        outcome="consent_order",
        monetary_relief="$164,000 (penalty)",
        evidence=[{
            "quote": "Between 2017 and at least 2022, a significant majority of BloomTech's students funded their enrollment in its programs with an ISA.",
            "source_url": "https://files.consumerfinance.gov/f/documents/cfpb_bloomtech-inc-consent-order_2024-04.pdf",
            "section": "CFPB Consent Order 2024-CFPB-0001, ¶15",
        }],
    ),
    entry(
        precedent_id="prec.cfpb.goldman_apple_card_2024",
        source="Consumer Financial Protection Bureau",
        source_url="https://www.consumerfinance.gov/enforcement/actions/goldman-sachs-bank-usa/",
        date="2024-10-23",
        title="CFPB v. Goldman Sachs — deceptive Apple Card Monthly Installments marketing",
        summary="Goldman Sachs was ordered to pay $19.8 million in redress and a $45 million penalty after the CFPB found it misled Apple Card customers about automatic ACMI enrollment and refund application.",
        why_this_matters="Big-tech co-branded financial product ad/servicing precedent on installment financing disclosures.",
        retrieval_keywords=["Goldman Sachs", "Apple Card", "ACMI", "installments", "deceptive marketing", "Apple"],
        category_ids=["financial", "misleading"],
        violated_clause_ids=["cfpb.finance.actually_available_terms", "cfpb.finance.trigger_terms"],
        canonical_ids=["finance.misleading_or_unbalanced_claims", "finance.credit_advertising_trigger_terms"],
        outcome="consent_order",
        monetary_relief="$64,800,000 (redress + penalty)",
        evidence=[{
            "quote": "The Bureau found that Goldman engaged in deceptive acts or practices by misleading consumers to expect that purchases of Apple devices would automatically be enrolled in ACMI, and by misleading consumers enrolled in ACMI about the application of refunds to Apple Card accounts with both ACMI and non-ACMI balances.",
            "source_url": "https://www.consumerfinance.gov/enforcement/actions/goldman-sachs-bank-usa/",
            "section": "CFPB Enforcement Action Summary",
        }],
    ),
]

STATE_AG_PHASE3 = [
    entry(
        precedent_id="prec.nyag.4kapps_healthcare_2024",
        source="New York State Attorney General",
        source_url="https://ag.ny.gov/press-release/2024/attorney-general-james-secures-15-million-digital-marketing-company-misleading",
        date="2024-08-15",
        title="NY AG v. 4K Apps — deceptive healthcare lead-generation directories",
        summary="4K Apps paid $1.5 million after the NY AG found it ran deceptive mental-health and substance-abuse directories that routed callers to paid clients instead of listed facilities.",
        why_this_matters="Healthcare lead-gen ad precedent on directory misdirection and treatment-facility bait-and-switch.",
        retrieval_keywords=["4K Apps", "New York AG", "mental health", "lead generation", "healthcare marketing", "deceptive directories"],
        category_ids=["health", "misleading"],
        violated_clause_ids=["ftc.health.material_safety_disclosure", "google.health.unauthorized_pharmacies"],
        canonical_ids=["health.health_privacy_sensitive_attributes", "misleading.false_affiliation_or_endorsement"],
        outcome="settlement",
        monetary_relief="$1,500,000",
        evidence=[{
            "quote": "The Office of the Attorney General (OAG) found that 4K Apps created dozens of websites that claimed to help consumers find and connect with health care and other services, but once consumers went onto those websites, they were shown phone numbers for 4K Apps' clients, not the facilities listed.",
            "source_url": "https://ag.ny.gov/press-release/2024/attorney-general-james-secures-15-million-digital-marketing-company-misleading",
            "section": "NY AG Press Release, August 2024",
        }],
    ),
    entry(
        precedent_id="prec.nyag.cameo_endorsements_2024",
        source="New York State Attorney General",
        source_url="https://ag.ny.gov/press-release/2024/attorney-general-james-secures-100000-cameo-over-misleading-videos",
        date="2024-06-12",
        title="NY AG v. Cameo — undisclosed Business Cameo paid endorsements",
        summary="Cameo paid $100,000 in a 30-state settlement after regulators found Business Cameo celebrity videos lacked required paid-endorsement disclosures.",
        why_this_matters="Celebrity/influencer platform precedent for paid endorsement labeling in short-form video ads.",
        retrieval_keywords=["Cameo", "Business Cameo", "paid endorsement", "influencer disclosure", "FTC Endorsement Guides", "celebrity ads"],
        category_ids=["misleading", "financial"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "sec.finance.testimonials"],
        canonical_ids=["finance.testimonials_endorsements_disclosure", "misleading.false_affiliation_or_endorsement"],
        outcome="settlement",
        monetary_relief="$100,000",
        evidence=[{
            "quote": "The Office of the Attorney General (OAG) found that Cameo failed to implement measures to ensure those videos were properly disclosed as paid endorsements, which violated endorsement rules issued by the Federal Trade Commission (FTC) and New York's consumer protection laws.",
            "source_url": "https://ag.ny.gov/press-release/2024/attorney-general-james-secures-100000-cameo-over-misleading-videos",
            "section": "NY AG Press Release, June 2024",
        }],
    ),
    entry(
        precedent_id="prec.nyag.google_iheart_pixel_2022",
        source="New York State Attorney General / FTC",
        source_url="https://ag.ny.gov/press-release/2022/attorney-general-james-secures-94-million-google-and-iheartmedia-over-misleading",
        date="2022-11-28",
        title="NY AG/FTC v. Google and iHeartMedia — fake Pixel 4 radio endorsements",
        summary="Google and iHeartMedia paid $9.4 million after regulators found radio personalities recorded Pixel 4 endorsement ads describing personal use of a phone they had never used.",
        why_this_matters="Landmark false personal-experience endorsement case for audio and influencer-style ads.",
        retrieval_keywords=["Google Pixel 4", "iHeartMedia", "radio ads", "false endorsement", "influencer", "$9.4 million"],
        category_ids=["misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "google.misrep.misleading_representation"],
        canonical_ids=["misleading.false_affiliation_or_endorsement", "finance.testimonials_endorsements_disclosure"],
        outcome="settlement",
        monetary_relief="$9,400,000",
        evidence=[{
            "quote": "Google paid radio personalities to record endorsement ads describing their positive experience using the Google Pixel 4 phone, however, they had never used the phone prior to recording or running the ads.",
            "source_url": "https://ag.ny.gov/press-release/2022/attorney-general-james-secures-94-million-google-and-iheartmedia-over-misleading",
            "section": "NY AG Press Release, November 2022",
        }],
    ),
    entry(
        precedent_id="prec.caag.roomster_fake_reviews_2023",
        source="California Attorney General / FTC",
        source_url="https://oag.ca.gov/news/press-releases/attorney-general-bonta-announces-settlement-room-rental-app-purchasing-fake",
        date="2023-08-30",
        title="CA AG/FTC v. Roomster — purchased fake app reviews and false verification",
        summary="Roomster settled after a multi-state suit alleging it bought at least 20,000 fake positive app-store reviews and falsely claimed listings were verified and authentic.",
        why_this_matters="Joint state/FTC fake-review enforcement tied to the 2024 FTC reviews rule — app-store ad manipulation.",
        retrieval_keywords=["Roomster", "fake reviews", "app store", "California AG", "verified listings", "astroturfing"],
        category_ids=["misleading"],
        violated_clause_ids=["ftc.misleading.reasonable_basis", "google.misrep.unreliable_claims"],
        canonical_ids=["misleading.unsubstantiated_objective_claims", "misleading.false_affiliation_or_endorsement"],
        outcome="settlement",
        monetary_relief="$1,600,000 (multi-state)",
        evidence=[{
            "quote": "An investigation into Roomster found that the company purchased at least 20,000 fake positive reviews for its app in the Google and Apple app stores.",
            "source_url": "https://oag.ca.gov/news/press-releases/attorney-general-bonta-files-lawsuit-against-room-rental-app-purchasing-fake",
            "section": "CA AG Press Release, August 2022 lawsuit",
        }],
    ),
    entry(
        precedent_id="prec.caag.cri_genetics_2024",
        source="California Attorney General / FTC",
        source_url="https://oag.ca.gov/news/press-releases/attorney-general-bonta-and-ftc-announce-settlement-cri-genetics-over-deceptive",
        date="2024-05-20",
        title="CA AG/FTC v. CRI Genetics — deceptive DNA test marketing",
        summary="CRI Genetics paid $700,000 in civil penalties after regulators alleged it misrepresented test accuracy, operated a fake independent review site, and used false testimonials.",
        why_this_matters="Direct-to-consumer genetic test ad precedent on accuracy claims, fake review sites, and health testimonials.",
        retrieval_keywords=["CRI Genetics", "DNA testing", "fake reviews", "health claims", "California AG", "genetic ancestry"],
        category_ids=["health", "misleading"],
        violated_clause_ids=["ftc.health.material_safety_disclosure", "google.health.speculative_experimental"],
        canonical_ids=["health.unsubstantiated_health_claims", "misleading.unsubstantiated_objective_claims"],
        outcome="settlement",
        monetary_relief="$700,000",
        evidence=[{
            "quote": "CRI created a genetics testing review website deceptively formatted to look independent. Through that website, CRI provided inflated reviews of its genetic testing services.",
            "source_url": "https://oag.ca.gov/news/press-releases/attorney-general-bonta-and-ftc-announce-settlement-cri-genetics-over-deceptive",
            "section": "CA AG Press Release, May 2024",
        }],
    ),
]

DOJ_PHASE3 = [
    entry(
        precedent_id="prec.doj.liao_apple_counterfeit_2022",
        source="U.S. Department of Justice",
        source_url="https://www.justice.gov/usao-sdca/pr/leaders-international-organization-trafficked-counterfeit-apple-products-plead-guilty",
        date="2022-05-19",
        title="DOJ v. Liao brothers — counterfeit Apple warranty fraud scheme",
        summary="Three Liao brothers pleaded guilty to leading an international conspiracy that exchanged more than 10,000 counterfeit iPhones and iPads at Apple Stores, causing about $6.1 million in losses.",
        why_this_matters="Criminal counterfeit-goods precedent distinct from marketplace listing cases — warranty-return fraud ring.",
        retrieval_keywords=["Liao", "counterfeit iPhone", "Apple", "trademark", "warranty fraud", "$6.1 million"],
        category_ids=["ip_trademark", "misleading"],
        violated_clause_ids=["google.ip.counterfeit_goods", "meta.ip.counterfeit_goods"],
        canonical_ids=["ip.counterfeit_goods_prohibited"],
        outcome="court_order",
        monetary_relief="$6,100,000 (estimated infringement)",
        evidence=[{
            "quote": "At the direction of the Liao brothers, co-conspirators traveled to hundreds of Apple Stores across the United States and Canada and attempted to exchange more than 10,000 counterfeit iPhones and iPads for genuine iPhones and iPads.",
            "source_url": "https://www.justice.gov/usao-sdca/pr/leaders-international-organization-trafficked-counterfeit-apple-products-plead-guilty",
            "section": "DOJ USAO Southern District of California",
        }],
    ),
    entry(
        precedent_id="prec.doj.bugaboo_boutique_counterfeit_2025",
        source="U.S. Department of Justice",
        source_url="https://www.justice.gov/usao-ne/pr/columbus-woman-convicted-trafficking-counterfeit-goods",
        date="2025-01-16",
        title="DOJ v. Bugaboo Boutique — online counterfeit goods trafficking",
        summary="Christine Parry was sentenced for trafficking counterfeit trademarked clothing, footwear, and accessories sold through the Bugaboo Boutique online store on Facebook.",
        why_this_matters="Social-commerce counterfeit enforcement — Facebook storefront selling 'inspired by' knockoffs with identical marks.",
        retrieval_keywords=["Bugaboo Boutique", "counterfeit", "Facebook store", "trademark", "online trafficking", "Nebraska"],
        category_ids=["ip_trademark", "misleading"],
        violated_clause_ids=["meta.ip.counterfeit_goods", "google.ip.counterfeit_goods"],
        canonical_ids=["ip.counterfeit_goods_prohibited"],
        outcome="court_order",
        monetary_relief="$12,000 fine + restitution",
        evidence=[{
            "quote": "The records revealed that Parry knowingly sold counterfeit goods through their online store. The counterfeit goods were described using words such as \"inspired by\" name brand goods.",
            "source_url": "https://www.justice.gov/usao-ne/pr/columbus-woman-convicted-trafficking-counterfeit-goods",
            "section": "DOJ USAO District of Nebraska, January 2025",
        }],
    ),
    entry(
        precedent_id="prec.doj.apple_sony_counterfeit_import_2016",
        source="U.S. Department of Justice",
        source_url="https://www.justice.gov/opa/pr/four-individuals-charged-importing-and-trafficking-counterfeit-apple-and-sony-technology",
        date="2016-03-01",
        title="DOJ — smuggling counterfeit Apple and Sony electronics",
        summary="Four individuals were charged with importing and trafficking more than 40,000 counterfeit Apple and Sony devices and accessories with an MSRP exceeding $15 million.",
        why_this_matters="Import/smuggling ring precedent complementing ecommerce listing enforcement — bulk counterfeit ad supply chain.",
        retrieval_keywords=["counterfeit Apple", "Sony", "smuggling", "import", "trademark trafficking", "$15 million MSRP"],
        category_ids=["ip_trademark"],
        violated_clause_ids=["google.ip.counterfeit_goods", "amazon.misleading.truthful_substantiated_claims"],
        canonical_ids=["ip.counterfeit_goods_prohibited"],
        outcome="court_order",
        monetary_relief="$15,000,000+ (MSRP equivalent)",
        evidence=[{
            "quote": "From July 2009 through February 2014, the defendants conspired to smuggle into the United States from China over 40,000 electronic devices and accessories, including fake iPads, iPhones and iPods, along with labels and packaging, most bearing counterfeit Apple trademarks.",
            "source_url": "https://www.justice.gov/opa/pr/four-individuals-charged-importing-and-trafficking-counterfeit-apple-and-sony-technology",
            "section": "DOJ Office of Public Affairs, March 2016",
        }],
    ),
]

TTB_PHASE3 = [
    entry(
        precedent_id="prec.ttb.fifth_generation_sponsorship_2022",
        source="Alcohol and Tobacco Tax and Trade Bureau",
        source_url="https://www.ttb.gov/public-information/press/press-release-fy-22-3",
        date="2022-01-24",
        title="TTB v. Fifth Generation — unlawful spirits sponsorship trade practices",
        summary="TTB accepted a $305,000 offer in compromise from Fifth Generation (Tito's) for sponsorship agreements that allegedly excluded competitors' products at venue concessions.",
        why_this_matters="Alcohol trade-practice enforcement on sponsorship-driven exclusivity in venue marketing.",
        retrieval_keywords=["TTB", "Fifth Generation", "Tito's", "sponsorship", "trade practices", "FAA Act", "$305000"],
        category_ids=["alcohol", "misleading"],
        violated_clause_ids=["google.atc.alcohol", "meta.atc.alcohol"],
        canonical_ids=["atc.alcohol_mandatory_and_prohibited_statements"],
        outcome="settlement",
        monetary_relief="$305,000",
        evidence=[{
            "quote": "As a result of an investigation into sponsorship agreements that allegedly resulted in the unlawful exclusion of their competitors' products, TTB has accepted a $305,000 Offer in Compromise (OIC) from Fifth Generation, Inc. of Austin, Texas.",
            "source_url": "https://www.ttb.gov/public-information/press/press-release-fy-22-3",
            "section": "TTB Press Release FY-22-3",
        }],
    ),
]

FEC_PHASE3 = [
    entry(
        precedent_id="prec.fec.moderate_pac_disclosure_2024",
        source="Federal Election Commission",
        source_url="https://www.fec.gov/files/legal/murs/8196/8196_12.pdf",
        date="2024-05-08",
        title="FEC v. Moderate PAC — late independent expenditure reporting",
        summary="The Moderate PAC agreed to pay a $58,000 civil penalty for failing to timely file five 24-hour reports covering $582,652 in pre-election independent expenditures.",
        why_this_matters="Recent PAC independent-expenditure disclosure enforcement for late 24-hour IE reports in federal elections.",
        retrieval_keywords=["Moderate PAC", "24-hour report", "independent expenditure", "FEC", "disclosure", "$58000"],
        category_ids=["political"],
        violated_clause_ids=["fec.political.disclaimer", "google.political.paid_for_by"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="fine",
        monetary_relief="$58,000",
        evidence=[{
            "quote": "Respondent will pay a civil penalty to the Federal Election Commission in the amount of Fifty-Eight Thousand Dollars ($58,000) pursuant to 52 U.S.C. § 30109(a)(5)(A).",
            "source_url": "https://www.fec.gov/files/legal/murs/8196/8196_12.pdf",
            "section": "MUR 8196 Conciliation Agreement, Section VI",
        }],
    ),
    entry(
        precedent_id="prec.fec.black_voters_matter_24hour_2024",
        source="Federal Election Commission",
        source_url="https://www.fec.gov/files/legal/murs/8353/8353_09.pdf",
        date="2024-03-15",
        title="FEC v. Black Voters Matter PAC — late IE 24-hour reports (2022 Georgia)",
        summary="Black Voters Matter Action PAC agreed to pay a $16,000 penalty for failing to timely file 24-hour reports for $158,018 in pre-election independent expenditures supporting Raphael Warnock.",
        why_this_matters="State-targeted IE ad disclosure enforcement — late 24-hour reporting in high-spend Senate races.",
        retrieval_keywords=["Black Voters Matter", "24-hour report", "independent expenditure", "Warnock", "FEC", "Georgia"],
        category_ids=["political"],
        violated_clause_ids=["fec.political.disclaimer", "meta.political.authorization_disclaimer"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="fine",
        monetary_relief="$16,000",
        evidence=[{
            "quote": "Respondent violated 52 U.S.C. § 30104(g)(1) and 11 C.F.R. § 104.4(c) by failing to file the required 24-hour reports for independent expenditures totaling $158,018.",
            "source_url": "https://www.fec.gov/files/legal/murs/8353/8353_09.pdf",
            "section": "MUR 8353 Conciliation Agreement, Section V",
        }],
    ),
]

PLATFORMS_PHASE3 = [
    entry(
        precedent_id="prec.meta.ads_takedown_metrics_q1_2024",
        source="Meta Transparency Center",
        source_url="https://transparency.meta.com/reports/integrity-reports-q1-2024/",
        date="2024-04-01",
        title="Meta Q1 2024 — ads takedown metrics broken out separately",
        summary="Meta's Q1 2024 integrity reporting for the first time separately reports ads takedowns from proactive enforcement and from user reports, previously bundled in overall Facebook/Instagram volumes.",
        why_this_matters="Platform transparency milestone for ad-specific enforcement metrics — baseline for ad rejection benchmarking.",
        retrieval_keywords=["Meta", "ads takedowns", "integrity report", "Q1 2024", "proactive enforcement", "transparency"],
        category_ids=["misleading"],
        violated_clause_ids=["meta.misleading.deceptive_practices"],
        canonical_ids=["misleading.unsubstantiated_objective_claims"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "We've also improved our transparency reporting by adding more metrics like ads takedowns based on reports we received, as well as proactive actions — the former of which was previously included in the overall Facebook and Instagram enforcement volumes but is now broken out separately for the first time.",
            "source_url": "https://transparency.meta.com/reports/integrity-reports-q1-2024/",
            "section": "Meta Integrity Reports Q1 2024",
        }],
    ),
    entry(
        precedent_id="prec.meta.ai_political_ad_disclosure_2024",
        source="Meta Transparency Center",
        source_url="https://transparency.meta.com/reports/integrity-reports-q1-2024/",
        date="2024-04-01",
        title="Meta Q1 2024 — GenAI disclosure requirements for political ads",
        summary="Meta reported requiring advertisers to disclose when political or social-issue ads use third-party generative AI to digitally create or alter content.",
        why_this_matters="First platform policy requiring GenAI disclosure on political/social-issue ads — synthetic media compliance.",
        retrieval_keywords=["Meta", "generative AI", "political ads", "Made with AI", "synthetic media", "disclosure"],
        category_ids=["political", "misleading"],
        violated_clause_ids=["meta.political.authorization_disclaimer", "google.political.synthetic_content"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "In certain cases, we also require advertisers to disclose when they digitally create or alter a political or social issue ad using third-party GenAI tools.",
            "source_url": "https://transparency.meta.com/reports/integrity-reports-q1-2024/",
            "section": "Meta Integrity Reports Q1 2024",
        }],
    ),
    entry(
        precedent_id="prec.tiktok.deceptive_behavior_enforcement_2024",
        source="TikTok Newsroom",
        source_url="https://newsroom.tiktok.com/how-tiktok-counters-deceptive-behaviour?from_seo_redirect=1&lang=en-150",
        date="2024-08-01",
        title="TikTok Q2 2024 — proactive fake-engagement enforcement",
        summary="TikTok reported removing over 99% of fake-engagement violating videos proactively in Q2 2024 and labeling state-affiliated media accounts restricted from foreign election influence ads.",
        why_this_matters="Platform enforcement metrics on deceptive engagement and covert influence — relevant to ad and organic promotion integrity.",
        retrieval_keywords=["TikTok", "fake engagement", "deceptive behavior", "covert influence", "proactive removal", "2024"],
        category_ids=["misleading", "political"],
        violated_clause_ids=["tiktok.misleading.unsubstantiated_claims", "tiktok.political.prohibited"],
        canonical_ids=["misleading.unsubstantiated_objective_claims", "political.paid_political_ads_prohibited"],
        outcome="suspension",
        monetary_relief=None,
        evidence=[{
            "quote": "In Q2 2024, over 99% of the videos that violate our fake engagement policy were removed proactively.",
            "source_url": "https://newsroom.tiktok.com/how-tiktok-counters-deceptive-behaviour?from_seo_redirect=1&lang=en-150",
            "section": "TikTok Newsroom, How TikTok counters deceptive behaviour",
        }],
    ),
    entry(
        precedent_id="prec.google.synthetic_election_ads_2024",
        source="Google Ads Policy",
        source_url="https://support.google.com/adspolicy/answer/6014595?hl=en",
        date="2024-01-01",
        title="Google election ads — synthetic and digitally altered content disclosure",
        summary="Google requires election advertisers in covered regions to disclose synthetic or digitally altered content in election ads and maintains verification and Paid for by requirements.",
        why_this_matters="Google election-ad synthetic media disclosure rule — pairs with Meta GenAI political ad requirements.",
        retrieval_keywords=["Google Ads", "election ads", "synthetic content", "AI disclosure", "Paid for by", "political verification"],
        category_ids=["political", "misleading"],
        violated_clause_ids=["google.political.synthetic_content", "google.political.paid_for_by"],
        canonical_ids=["political.authorization_and_disclaimer_required"],
        outcome="guidance",
        monetary_relief=None,
        evidence=[{
            "quote": "Google believes that users should have information to make informed decisions when viewing election ads that contain synthetic or digitally altered content, specifically images, video, or audio that inauthentically depict real or realistic-looking people or events.",
            "source_url": "https://support.google.com/adspolicy/answer/6014595?hl=en",
            "section": "Google Ads Policy — Political content (synthetic content)",
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
        FTC_PHASE3
        + SEC_PHASE3
        + FINRA_PHASE3
        + CFPB_PHASE3
        + STATE_AG_PHASE3
        + DOJ_PHASE3
        + TTB_PHASE3
        + FEC_PHASE3
        + PLATFORMS_PHASE3
    )
    verify_clauses(all_new)
    print(f"Generating {len(all_new)} Phase 3 precedents")

    dump_file(PREC / "ftc_phase3.yaml", "# FTC enforcement precedents — Phase 3 (final US expansion).", FTC_PHASE3)
    dump_file(PREC / "sec_phase3.yaml", "# SEC enforcement precedents — Phase 3 (crypto/NFT/staking).", SEC_PHASE3)
    dump_file(PREC / "finra.yaml", "# FINRA enforcement precedents.", merge_precedents(PREC / "finra.yaml", FINRA_PHASE3))
    dump_file(PREC / "cfpb.yaml", "# CFPB enforcement precedents.", merge_precedents(PREC / "cfpb.yaml", CFPB_PHASE3))
    dump_file(PREC / "state_ag.yaml", "# State Attorney General enforcement precedents.", merge_precedents(PREC / "state_ag.yaml", STATE_AG_PHASE3))
    dump_file(PREC / "doj.yaml", "# DOJ enforcement precedents (non-HUD seed cases).", merge_precedents(PREC / "doj.yaml", DOJ_PHASE3))
    dump_file(PREC / "ttb.yaml", "# TTB alcohol advertising enforcement.", merge_precedents(PREC / "ttb.yaml", TTB_PHASE3))
    dump_file(PREC / "fec.yaml", "# FEC political advertising precedents.", merge_precedents(PREC / "fec.yaml", FEC_PHASE3))
    dump_file(PREC / "platforms.yaml", "# Platform policy enforcement precedents (official transparency/policy pages).", merge_precedents(PREC / "platforms.yaml", PLATFORMS_PHASE3))


if __name__ == "__main__":
    main()
