"""
Compliance pipeline engine.

Uses domain extractors (BaseExtractor) and declarative policies (YAML).
Orchestration delegates to ZetaOne core when available; this module
provides domain-specific rule checking and outcome assembly.
"""

from typing import List, Tuple, Optional
import sys
import os
import re
import uuid
from datetime import datetime

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import yaml

from schemas.models import (
    Asset, Signal, Violation, Outcome, ComplianceStatus,
    ViolationSeverity, Evidence, SignalType, Verdict,
)
from extractors.ocr_extractor import OCRExtractor
from extractors.vision_extractor import VisionExtractor
from extractors.embedding_extractor import EmbeddingExtractor
from extractors.vlm_extractor import VLMExtractor
from mappings.vision_support import VISION_SUPPORT_MAP
from mappings.embedding_rules import EMBEDDING_RULE_MAP


def _load_yaml(rel_path: str) -> dict:
    """Load YAML file relative to ad_compliance domain root."""
    domain_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(domain_root, rel_path)
    with open(path, "r") as f:
        return yaml.safe_load(f)


def _load_rules() -> dict:
    """Load compliance rules from policies/meta_ads.yaml."""
    data = _load_yaml("policies/meta_ads.yaml")
    return data.get("rules", {})


def _load_config() -> dict:
    """Load config from configs/meta_ads_config.yaml."""
    return _load_yaml("configs/meta_ads_config.yaml")


def _get_embedding_regulation_texts(config: dict) -> List[Tuple[str, str]]:
    """Build regulation texts list from config for embedding extractor."""
    reg = config.get("embedding", {}).get("regulation_texts", {})
    return [(k, v) for k, v in reg.items()]


class CompliancePipeline:
    """
    Domain pipeline: extractors + policy rules + outcome assembly.
    Uses ZetaOne BaseExtractor interface for signal extraction.
    """

    def __init__(self):
        config = _load_config()
        vision_cfg = config.get("vision", {})
        embedding_cfg = config.get("embedding", {})
        pipeline_cfg = config.get("pipeline", {})

        self.ocr_extractor = OCRExtractor()
        self.vision_extractor = VisionExtractor(
            object_queries=vision_cfg.get("object_queries")
        )
        self.embedding_extractor = EmbeddingExtractor(
            regulation_texts=_get_embedding_regulation_texts(config),
            similarity_threshold=embedding_cfg.get("similarity_threshold", 0.6),
        )
        self.vlm_extractor = VLMExtractor()

        self._rules = _load_rules()
        self._verdict_threshold = pipeline_cfg.get("verdict_threshold", 0.7)
        self._confidence_threshold = pipeline_cfg.get("confidence_threshold", 0.85)
        self._severity_weights = config.get("severity_weights", {
            "LOW": 0.2, "MEDIUM": 0.4, "HIGH": 0.7, "CRITICAL": 1.0,
        })
        self._count_factor = pipeline_cfg.get("risk_count_factor", 0.03)
        self._severity_factor_critical = pipeline_cfg.get("severity_factor_critical", 0.2)
        self._severity_factor_high = pipeline_cfg.get("severity_factor_high", 0.1)

    def process(self, asset: Asset) -> Outcome:
        """Process asset through extractors and rule checking."""
        signals = self._extract_signals(asset)
        violations = self._check_rules(asset, signals)
        risk_score = self._calculate_risk_score(violations)
        status = self._determine_status(risk_score, violations)
        rule_confidence = self._calculate_rule_confidence(violations)
        routing_flag = None
        if rule_confidence < self._confidence_threshold:
            routing_flag = "borderline_requires_context"
            status = ComplianceStatus.REVIEW_REQUIRED
        verdict = self._determine_verdict(risk_score)
        fix_suggestions = self._generate_fix_suggestions(violations)
        self._maybe_attach_vlm_reasoning(asset, signals, violations, routing_flag, verdict, risk_score)

        outcome = Outcome(
            outcome_id=str(uuid.uuid4()),
            asset_id=asset.image_id,
            status=status,
            risk_score=risk_score,
            verdict=verdict,
            violations=violations,
            signals=signals,
            fix_suggestions=fix_suggestions,
            processed_at=datetime.now(),
        )
        if routing_flag:
            outcome.metadata["routing"] = routing_flag
        return outcome

    def _extract_signals(self, asset: Asset) -> List[Signal]:
        """Extract signals using domain extractors (BaseExtractor)."""
        signals = []
        for extractor in [
            self.ocr_extractor,
            self.vision_extractor,
            self.embedding_extractor,
            self.vlm_extractor,
        ]:
            try:
                extracted = extractor.extract(asset)
                if extracted:
                    signals.extend(extracted)
            except Exception:
                pass
        return signals

    def _check_rules(self, asset: Asset, signals: List[Signal]) -> List[Violation]:
        """Check signals against policy rules from meta_ads.yaml."""
        violations = []
        text_signals = [s for s in signals if s.signal_type == SignalType.TEXT]
        vision_object_signals = [
            s for s in signals
            if s.raw_data.get("type") == "vision_object"
        ]
        embedding_signals_by_regulation = {}
        for s in signals:
            if s.raw_data.get("type") != "image_embedding_similarity":
                continue
            reg = s.raw_data.get("regulation")
            if reg:
                embedding_signals_by_regulation.setdefault(reg, []).append(s)

        rule_matches = {}
        for signal in text_signals:
            text_content = signal.raw_data.get("text", "").lower()
            for rule_id, rule in self._rules.items():
                match_result = self._matches_rule(text_content, rule)
                if match_result:
                    matched_term, confidence = match_result
                    if rule_id not in rule_matches:
                        rule_matches[rule_id] = []
                    rule_matches[rule_id].append((signal, matched_term, confidence))

        vision_triggered_rules = {}
        for rule_id, rule in self._rules.items():
            primary_labels = rule.get("vision_primary_labels")
            if not primary_labels:
                continue
            allowed = {str(l).strip().lower() for l in primary_labels}
            matched = [
                s for s in vision_object_signals
                if str(s.raw_data.get("label", "")).strip().lower() in allowed
            ]
            if matched:
                vision_triggered_rules[rule_id] = matched

        vision_primary_rule_ids = {
            r for r, rule in self._rules.items() if rule.get("vision_primary_labels")
        }
        ocr_triggered_ids = set(rule_matches.keys()) - vision_primary_rule_ids
        all_violation_rule_ids = ocr_triggered_ids | set(vision_triggered_rules.keys())

        for rule_id in all_violation_rule_ids:
            rule = self._rules[rule_id]
            matches = rule_matches.get(rule_id, [])
            vision_signals = vision_triggered_rules.get(rule_id, [])
            evidence_list = []

            for signal, matched_term, confidence in matches:
                evidence_list.append(
                    Evidence(
                        evidence_id=str(uuid.uuid4()),
                        violation_id="",
                        signal_id=signal.signal_id,
                        evidence_type="text_match",
                        description=f"{rule['name']} detected: '{matched_term}'",
                        data={
                            "matched_text": signal.raw_data.get("text", ""),
                            "matched_term": matched_term,
                            "confidence": confidence,
                            "signal_confidence": signal.confidence,
                            "ocr_text": signal.raw_data.get("text", ""),
                            "bbox": signal.bounding_box,
                        },
                    )
                )
            for s in vision_signals:
                evidence_list.append(
                    Evidence(
                        evidence_id=str(uuid.uuid4()),
                        violation_id="",
                        signal_id=s.signal_id,
                        evidence_type="vision_object",
                        description=f"Prohibited object detected: {s.raw_data.get('label')}",
                        data={
                            "label": s.raw_data.get("label"),
                            "confidence": 1.0,
                            "signal_confidence": s.confidence,
                            "bbox": s.raw_data.get("bbox"),
                            "model": s.raw_data.get("model", "grounding_dino"),
                        },
                    )
                )
            if vision_signals and not matches:
                for signal in text_signals:
                    text_content = signal.raw_data.get("text", "").lower()
                    match_result = self._matches_rule(text_content, rule)
                    if match_result:
                        matched_term, confidence = match_result
                        evidence_list.append(
                            Evidence(
                                evidence_id=str(uuid.uuid4()),
                                violation_id="",
                                signal_id=signal.signal_id,
                                evidence_type="text_match",
                                description=f"{rule['name']} (OCR): '{matched_term}'",
                                data={
                                    "matched_text": signal.raw_data.get("text", ""),
                                    "matched_term": matched_term,
                                    "confidence": confidence,
                                    "signal_confidence": signal.confidence,
                                    "ocr_text": signal.raw_data.get("text", ""),
                                    "bbox": signal.bounding_box,
                                },
                            )
                        )

            regulation_name = EMBEDDING_RULE_MAP.get(rule_id)
            if regulation_name:
                for signal in embedding_signals_by_regulation.get(regulation_name, []):
                    evidence_list.append(
                        Evidence(
                            evidence_id=str(uuid.uuid4()),
                            violation_id="",
                            signal_id=signal.signal_id,
                            evidence_type="image_embedding_similarity",
                            description="Embedding similarity support signal",
                            data={
                                "score": signal.raw_data.get("score", 0.0),
                                "model": signal.raw_data.get("model", "siglip"),
                                "confidence": 0.2,
                                "signal_confidence": signal.confidence,
                            },
                        )
                    )

            if rule_id in VISION_SUPPORT_MAP and vision_object_signals:
                allowed = VISION_SUPPORT_MAP[rule_id]
                matched_vision = [
                    s for s in vision_object_signals
                    if str(s.raw_data.get("label", "")).strip().lower() in allowed
                ]
                if matched_vision:
                    for ev in evidence_list:
                        if ev.evidence_type != "text_match":
                            continue
                        base = float(ev.data.get("confidence", 0.0))
                        ev.data["confidence"] = min(1.0, base + 0.1)
                    for s in matched_vision:
                        evidence_list.append(
                            Evidence(
                                evidence_id=str(uuid.uuid4()),
                                violation_id="",
                                signal_id=s.signal_id,
                                evidence_type="vision_object",
                                description=f"Vision object support: {s.raw_data.get('label')}",
                                data={
                                    "label": s.raw_data.get("label"),
                                    "confidence": 1.0,
                                    "signal_confidence": s.confidence,
                                    "bbox": s.raw_data.get("bbox"),
                                    "model": s.raw_data.get("model", "grounding_dino"),
                                },
                            )
                        )

            if evidence_list:
                total_confidence = sum(
                    e.data["confidence"] * e.data["signal_confidence"]
                    for e in evidence_list
                )
                avg_confidence = total_confidence / len(evidence_list)
            else:
                avg_confidence = 0.8

            violation = Violation(
                violation_id=str(uuid.uuid4()),
                rule_id=rule_id,
                rule_name=rule["name"],
                severity=ViolationSeverity(rule["severity"]),
                description=rule["description"],
                evidence=evidence_list,
            )
            for evidence in violation.evidence:
                evidence.violation_id = violation.violation_id
            violations.append(violation)

        return violations

    def _matches_rule(self, text: str, rule: dict) -> Optional[Tuple[str, float]]:
        """Check if text matches a rule. Returns (matched_term, confidence) or None."""
        for pat in rule.get("exception_patterns", []):
            if re.search(pat, text, re.IGNORECASE):
                return None
        text_lower = text.lower()
        for term in rule.get("exception_terms", []):
            if term.lower() in text_lower:
                return None
        context_terms = rule.get("context_terms", [])
        if context_terms:
            if not any(t.lower() in text_lower for t in context_terms):
                return None
        for pattern_info in rule.get("patterns", []):
            pattern = pattern_info.get("pattern", "")
            confidence = pattern_info.get("confidence", 0.9)
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return (match.group(0), confidence)
        for term in rule.get("prohibited_terms", []):
            term_lower = term.lower()
            if term_lower in text:
                text_with_spaces = f" {text} "
                if f" {term_lower} " in text_with_spaces:
                    return (term, 0.95)
                return (term, 0.85)
        return None

    def _calculate_risk_score(self, violations: List[Violation]) -> float:
        """Calculate overall risk score from violations."""
        if not violations:
            return 0.0
        total_weighted_risk = 0.0
        total_weight = 0.0
        for violation in violations:
            if violation.evidence:
                avg_confidence = sum(
                    e.data.get("confidence", 0.8) * e.data.get("signal_confidence", 0.8)
                    for e in violation.evidence
                ) / len(violation.evidence)
            else:
                avg_confidence = 0.8
            base_risk = self._severity_weights.get(violation.severity.value, 0.5)
            total_weighted_risk += base_risk * avg_confidence
            total_weight += avg_confidence
        base_score = total_weighted_risk / total_weight if total_weight > 0 else 0.5
        count_factor = min(len(violations) * self._count_factor, 0.15)
        has_critical = any(v.severity == ViolationSeverity.CRITICAL for v in violations)
        has_high = any(v.severity == ViolationSeverity.HIGH for v in violations)
        severity_factor = (
            self._severity_factor_critical if has_critical
            else self._severity_factor_high if has_high else 0.0
        )
        return round(min(base_score + count_factor + severity_factor, 1.0), 3)

    def _calculate_rule_confidence(self, violations: List[Violation]) -> float:
        """Calculate rule-based confidence from violations."""
        if not violations:
            return 1.0
        confidence_values = []
        for violation in violations:
            if violation.evidence:
                vc = sum(
                    e.data.get("confidence", 0.8) * e.data.get("signal_confidence", 0.8)
                    for e in violation.evidence
                ) / len(violation.evidence)
                confidence_values.append(vc)
            else:
                confidence_values.append(0.8)
        return round(sum(confidence_values) / len(confidence_values), 3)

    def _determine_status(self, risk_score: float, violations: List[Violation]) -> ComplianceStatus:
        if risk_score == 0.0:
            return ComplianceStatus.COMPLIANT
        if risk_score >= 0.7:
            return ComplianceStatus.NON_COMPLIANT
        return ComplianceStatus.REVIEW_REQUIRED

    def _determine_verdict(self, risk_score: float) -> Verdict:
        if risk_score > self._verdict_threshold:
            return Verdict.LIKELY_REJECTED
        if risk_score >= 0.3:
            return Verdict.BORDERLINE
        return Verdict.LIKELY_APPROVED

    def _generate_fix_suggestions(self, violations: List[Violation]) -> List[str]:
        suggestions = []
        seen_rules = set()
        for violation in violations:
            if violation.rule_id in seen_rules:
                continue
            seen_rules.add(violation.rule_id)
            if violation.rule_id == "misleading_exaggerated_claims":
                matched_terms = set()
                for evidence in violation.evidence:
                    term = evidence.data.get("matched_term", "")
                    if term:
                        matched_terms.add(term.lower())
                if matched_terms:
                    terms_list = ", ".join(sorted(matched_terms))
                    suggestions.append(
                        f"Remove or rephrase misleading claims: {terms_list}. "
                        "Replace absolute guarantees with qualified statements."
                    )
                    suggestions.append(
                        "Avoid exaggerated timeframes (e.g., 'instant', 'overnight'). "
                        "Use realistic expectations and timelines."
                    )
                    if any("100%" in t or "%" in t for t in matched_terms):
                        suggestions.append(
                            "Remove percentage-based guarantees. "
                            "Use descriptive language instead of absolute percentages."
                        )
                    if any("lose" in t for t in matched_terms):
                        suggestions.append(
                            "Avoid specific weight loss timeframes. "
                            "Focus on general health benefits rather than rapid results."
                        )
            elif violation.rule_id == "biopharma_prohibited_claims":
                suggestions.append(
                    "Remove medical claims that imply cure or guarantee. "
                    "Use language like 'may support' or 'designed to help' instead."
                )
            elif violation.rule_id == "finance_prohibited_claims":
                suggestions.append(
                    "Remove financial guarantees and risk-free claims. "
                    "Include appropriate disclaimers about investment risks."
                )
            if not suggestions or violation.severity in [ViolationSeverity.HIGH, ViolationSeverity.CRITICAL]:
                suggestions.append(
                    f"Review and revise content to address {violation.rule_name.lower()}. "
                    "Ensure all claims are substantiated and comply with advertising guidelines."
                )
        seen = set()
        unique = []
        for s in suggestions:
            if s not in seen:
                seen.add(s)
                unique.append(s)
        return unique[:5]

    def _maybe_attach_vlm_reasoning(
        self,
        asset: Asset,
        signals: List[Signal],
        violations: List[Violation],
        routing_flag: Optional[str],
        verdict: Verdict,
        risk_score: float,
    ) -> None:
        """Attach VLM context analysis for borderline cases only."""
        if routing_flag != "borderline_requires_context":
            return
        if not violations or verdict == Verdict.LIKELY_REJECTED or risk_score >= 0.7:
            return
        has_ocr_violation = any(
            any(ev.evidence_type == "text_match" for ev in v.evidence)
            for v in violations
        )
        if not has_ocr_violation:
            return
        ocr_texts = [
            s.raw_data.get("text", "")
            for s in signals
            if s.signal_type == SignalType.TEXT and s.raw_data.get("text")
        ]
        vision_objects = [s.raw_data for s in signals if s.raw_data.get("type") == "vision_object"]
        policy_id = next(
            (v.rule_id for v in violations if any(ev.evidence_type == "text_match" for ev in v.evidence)),
            violations[0].rule_id,
        )
        try:
            explanation = self.vlm_extractor.analyze_image_context(
                image_bytes=asset.image_data,
                ocr_texts=ocr_texts,
                vision_objects=vision_objects,
                policy_id=policy_id,
            )
        except Exception:
            explanation = "VLM analysis unavailable at this time."
        for violation in violations:
            violation.evidence.append(
                Evidence(
                    evidence_id=str(uuid.uuid4()),
                    violation_id=violation.violation_id,
                    signal_id="vlm_api",
                    evidence_type="vlm_reasoning_stub",
                    description="VLM context analysis (borderline only)",
                    data={"explanation": explanation},
                )
            )

    def _load_rules(self) -> dict:
        """Load rules (for /rules API endpoint)."""
        return _load_rules()
