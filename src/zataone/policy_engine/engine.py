# zataone policy engine

from __future__ import annotations

import re
from typing import Any

from zataone.document.flags import document_centric_enabled
from zataone.policy_engine.dsl.evaluator import DSLMatchResult, RuleEvaluator
from zataone.policy_engine.dsl.legacy_adapter import rule_to_match_ast
from zataone.policy_engine.dsl.ast import MatchAST
from zataone.policy_engine.match_span import locate_match_span, pick_signal_id_for_span
from zataone.policy_engine.rule import Rule
from zataone.schemas.document import DocumentSignal
from zataone.schemas.violation import Violation as ViolationSchema

_SEVERITY_WEIGHTS = {"LOW": 0.2, "MEDIUM": 0.4, "HIGH": 0.7, "CRITICAL": 1.0}


class PolicyEngine:
    """
    Deterministic policy evaluation engine.
    Policies are loaded from configuration (YAML/registry), never hard-coded.
    """

    def __init__(self) -> None:
        self._rules: dict[str, dict] = {}
        self._rule_asts: dict[str, MatchAST] = {}
        self._vision_support_map: dict = {}
        self._embedding_rule_map: dict = {}
        self._domain_schemas: Any = None
        self._active_rule_ids: set[str] | None = None

    def load_policy_pack(
        self,
        config_path: str | dict[str, Any] | None = None,
        rules: dict[str, Any] | None = None,
        vision_support_map: dict | None = None,
        embedding_rule_map: dict | None = None,
    ) -> list[Rule]:
        """
        Load policy pack from config file or dict.
        Returns list of Rule instances.
        """
        if rules is not None:
            self._rules = rules
        if vision_support_map is not None:
            self._vision_support_map = vision_support_map
        if embedding_rule_map is not None:
            self._embedding_rule_map = embedding_rule_map

        if config_path is not None and isinstance(config_path, dict):
            self._rules = config_path.get("rules", config_path)

        self._compile_rule_asts()
        return [Rule.from_config({"rule_id": k, **v}) for k, v in self._rules.items()]

    def _compile_rule_asts(self) -> None:
        self._rule_asts = {}
        for rule_id, rule in self._rules.items():
            ast = rule_to_match_ast(rule)
            if ast is not None:
                self._rule_asts[rule_id] = ast

    def set_active_rule_ids(self, rule_ids: set[str] | list[str] | None) -> None:
        """Deprecated: pass active_rule_ids directly to evaluate() instead."""
        if rule_ids is None:
            self._active_rule_ids = None
        else:
            self._active_rule_ids = set(rule_ids)

    def iter_rules(self) -> list[tuple[str, dict]]:
        """Iterate all rules (legacy; use _iter_rules_filtered for thread-safe per-call filtering)."""
        return list(self._rules.items())

    def _iter_rules_filtered(
        self, active_rule_ids: set[str] | None
    ) -> list[tuple[str, dict]]:
        if active_rule_ids is None:
            return list(self._rules.items())
        return [(rid, r) for rid, r in self._rules.items() if rid in active_rule_ids]

    def evaluate(
        self,
        signals: list[Any],
        policy_pack_id: str | None = None,
        rules: list[Rule] | None = None,
        document: DocumentSignal | None = None,
        active_rule_ids: set[str] | list[str] | None = None,
    ) -> list[ViolationSchema]:
        """
        Evaluate policies against signals. Returns List[Violation].

        active_rule_ids: restrict evaluation to this subset (e.g. from retrieval).
        Pass per-call instead of using set_active_rule_ids() for thread safety.
        """
        if not self._rules:
            return []

        effective_ids: set[str] | None = (
            set(active_rule_ids) if active_rule_ids is not None else self._active_rule_ids
        )

        if document_centric_enabled() and document is not None:
            return self._evaluate_with_document(signals, document, effective_ids)

        return self._evaluate_fragment_centric(signals, effective_ids)

    def _evaluate_with_document(
        self,
        signals: list[Any],
        document: DocumentSignal,
        active_rule_ids: set[str] | None = None,
    ) -> list[ViolationSchema]:
        text_signals = [s for s in signals if self._is_text_signal(s)]
        vision_object_signals = [
            s for s in signals
            if hasattr(s, "raw_data") and (s.raw_data or {}).get("type") == "vision_object"
        ]
        embedding_signals_by_regulation = self._embedding_by_regulation(signals)

        doc_text = document.normalized_text or ""
        rule_matches: dict[str, tuple[str, float, dict[str, Any] | None]] = {}

        for rule_id, rule in self._iter_rules_filtered(active_rule_ids):
            dsl_hit = self._match_rule(doc_text, rule_id, rule)
            if not dsl_hit:
                continue
            span = dsl_hit.span or locate_match_span(doc_text, dsl_hit.matched_term, rule)
            rule_matches[rule_id] = (dsl_hit.matched_term, dsl_hit.confidence, span)

        return self._assemble_violations(
            signals=signals,
            text_signals=text_signals,
            vision_object_signals=vision_object_signals,
            embedding_signals_by_regulation=embedding_signals_by_regulation,
            rule_matches={
                rid: [(None, mt, conf, sp)]
                for rid, (mt, conf, sp) in rule_matches.items()
            },
            document=document,
            document_centric=True,
            active_rule_ids=active_rule_ids,
        )

    def _evaluate_fragment_centric(
        self,
        signals: list[Any],
        active_rule_ids: set[str] | None = None,
    ) -> list[ViolationSchema]:
        text_signals = [s for s in signals if self._is_text_signal(s)]
        vision_object_signals = [
            s for s in signals
            if hasattr(s, "raw_data") and (s.raw_data or {}).get("type") == "vision_object"
        ]
        embedding_signals_by_regulation = self._embedding_by_regulation(signals)

        rule_matches: dict[str, list[tuple[Any, str, float, dict | None]]] = {}
        for signal in text_signals:
            text_content = (getattr(signal, "raw_data", {}) or {}).get("text", "")
            for rule_id, rule in self._iter_rules_filtered(active_rule_ids):
                dsl_hit = self._match_rule(text_content, rule_id, rule)
                if dsl_hit:
                    span = dsl_hit.span
                    rule_matches.setdefault(rule_id, []).append(
                        (signal, dsl_hit.matched_term, dsl_hit.confidence, span)
                    )

        return self._assemble_violations(
            signals=signals,
            text_signals=text_signals,
            vision_object_signals=vision_object_signals,
            embedding_signals_by_regulation=embedding_signals_by_regulation,
            rule_matches=rule_matches,
            document=None,
            document_centric=False,
            active_rule_ids=active_rule_ids,
        )

    def _assemble_violations(
        self,
        *,
        signals: list[Any],
        text_signals: list[Any],
        vision_object_signals: list[Any],
        embedding_signals_by_regulation: dict[str, list[Any]],
        rule_matches: dict[str, list[tuple[Any | None, str, float, dict | None]]],
        document: DocumentSignal | None,
        document_centric: bool,
        active_rule_ids: set[str] | None = None,
    ) -> list[ViolationSchema]:
        def _severity_to_float(sev: str) -> float:
            return _SEVERITY_WEIGHTS.get(str(sev), 0.5)

        def _make_evidence_data(evidence_type: str, data: dict, rule: dict) -> dict:
            out = {"evidence_type": evidence_type, "rule_name": rule.get("name", ""), **data}
            if document_centric:
                out["document_centric"] = True
            return out

        vision_triggered_rules = {}
        for rule_id, rule in self._iter_rules_filtered(active_rule_ids):
            primary_labels = rule.get("vision_primary_labels")
            if not primary_labels:
                continue
            allowed = {str(l).strip().lower() for l in primary_labels}
            matched = [
                s for s in vision_object_signals
                if str((s.raw_data or {}).get("label", "")).strip().lower() in allowed
            ]
            if matched:
                vision_triggered_rules[rule_id] = matched

        vision_primary_rule_ids = {
            r for r, rule in self._iter_rules_filtered(active_rule_ids) if rule.get("vision_primary_labels")
        }
        ocr_triggered_ids = set(rule_matches.keys()) - vision_primary_rule_ids
        all_violation_rule_ids = ocr_triggered_ids | set(vision_triggered_rules.keys())

        violations: list[ViolationSchema] = []
        doc_spans = document.spans if document else []

        for rule_id in all_violation_rule_ids:
            rule = self._rules[rule_id]
            matches = rule_matches.get(rule_id, [])
            vision_signals = vision_triggered_rules.get(rule_id, [])
            severity_float = _severity_to_float(rule.get("severity", "HIGH"))

            for match in matches:
                signal, matched_term, confidence, span = match
                if document_centric:
                    signal_id = pick_signal_id_for_span(
                        span,
                        doc_spans,
                        text_signals,
                        document.source_signal_ids if document else [],
                    )
                    ocr_excerpt = (document.normalized_text if document else "")[:500]
                    bbox = None
                    if span and doc_spans:
                        for dsp in doc_spans:
                            ds = getattr(dsp, "start", dsp.get("start") if isinstance(dsp, dict) else None)
                            if ds == span.get("start"):
                                bbox = getattr(dsp, "bbox", None) or (
                                    dsp.get("bbox") if isinstance(dsp, dict) else None
                                )
                                break
                else:
                    signal_id = str(getattr(signal, "signal_id", "unknown"))
                    ocr_excerpt = (getattr(signal, "raw_data", {}) or {}).get("text", "")
                    bbox = getattr(signal, "bounding_box", None)
                    span = None

                evidence_data = _make_evidence_data(
                    "text_match",
                    {
                        "matched_text": matched_term,
                        "matched_term": matched_term,
                        "confidence": confidence,
                        "signal_confidence": (
                            getattr(signal, "confidence", 0.8) if signal is not None else 0.8
                        ),
                        "ocr_text": ocr_excerpt,
                        "bbox": bbox,
                        "matched_span": span,
                        "document_excerpt": document.normalized_text[:2000] if document else ocr_excerpt,
                        "source_signal_ids": (
                            list(document.source_signal_ids) if document else [signal_id]
                        ),
                    },
                    rule,
                )
                violations.append(
                    ViolationSchema(
                        signal_id=signal_id,
                        rule_id=rule_id,
                        violation_type="text_match",
                        severity=severity_float,
                        evidence_data=evidence_data,
                    )
                )

            for s in vision_signals:
                signal_id = str(getattr(s, "signal_id", "unknown"))
                evidence_data = _make_evidence_data(
                    "vision_object",
                    {
                        "label": (s.raw_data or {}).get("label"),
                        "confidence": 1.0,
                        "signal_confidence": getattr(s, "confidence", 0.8),
                        "bbox": (s.raw_data or {}).get("bbox"),
                        "model": (s.raw_data or {}).get("model", "grounding_dino"),
                    },
                    rule,
                )
                violations.append(
                    ViolationSchema(
                        signal_id=signal_id,
                        rule_id=rule_id,
                        violation_type="vision_object",
                        severity=severity_float,
                        evidence_data=evidence_data,
                    )
                )

            if vision_signals and not matches:
                if document_centric and document:
                    dsl_hit = self._match_rule(document.normalized_text, rule_id, rule)
                    if dsl_hit:
                        matched_term = dsl_hit.matched_term
                        confidence = dsl_hit.confidence
                        span = dsl_hit.span or locate_match_span(
                            document.normalized_text, matched_term, rule
                        )
                        signal_id = pick_signal_id_for_span(
                            span, doc_spans, text_signals, document.source_signal_ids
                        )
                        evidence_data = _make_evidence_data(
                            "text_match",
                            {
                                "matched_text": matched_term,
                                "matched_term": matched_term,
                                "confidence": confidence,
                                "signal_confidence": 0.8,
                                "ocr_text": document.normalized_text[:500],
                                "bbox": None,
                                "matched_span": span,
                                "document_excerpt": document.normalized_text[:2000],
                                "source_signal_ids": list(document.source_signal_ids),
                            },
                            rule,
                        )
                        violations.append(
                            ViolationSchema(
                                signal_id=signal_id,
                                rule_id=rule_id,
                                violation_type="text_match",
                                severity=severity_float,
                                evidence_data=evidence_data,
                            )
                        )
                else:
                    for signal in text_signals:
                        text_content = (getattr(signal, "raw_data", {}) or {}).get("text", "")
                        dsl_hit = self._match_rule(text_content, rule_id, rule)
                        if dsl_hit:
                            matched_term = dsl_hit.matched_term
                            confidence = dsl_hit.confidence
                            signal_id = str(getattr(signal, "signal_id", "unknown"))
                            evidence_data = _make_evidence_data(
                                "text_match",
                                {
                                    "matched_text": (signal.raw_data or {}).get("text", ""),
                                    "matched_term": matched_term,
                                    "confidence": confidence,
                                    "signal_confidence": getattr(signal, "confidence", 0.8),
                                    "ocr_text": (signal.raw_data or {}).get("text", ""),
                                    "bbox": getattr(signal, "bounding_box", None),
                                },
                                rule,
                            )
                            violations.append(
                                ViolationSchema(
                                    signal_id=signal_id,
                                    rule_id=rule_id,
                                    violation_type="text_match",
                                    severity=severity_float,
                                    evidence_data=evidence_data,
                                )
                            )

            regulation_name = self._embedding_rule_map.get(rule_id)
            if regulation_name:
                for signal in embedding_signals_by_regulation.get(regulation_name, []):
                    signal_id = str(getattr(signal, "signal_id", "unknown"))
                    evidence_data = _make_evidence_data(
                        "image_embedding_similarity",
                        {
                            "score": (signal.raw_data or {}).get("score", 0.0),
                            "model": (signal.raw_data or {}).get("model", "siglip"),
                            "confidence": 0.2,
                            "signal_confidence": getattr(signal, "confidence", 0.8),
                        },
                        rule,
                    )
                    violations.append(
                        ViolationSchema(
                            signal_id=signal_id,
                            rule_id=rule_id,
                            violation_type="image_embedding_similarity",
                            severity=severity_float,
                            evidence_data=evidence_data,
                        )
                    )

            if rule_id in self._vision_support_map and vision_object_signals:
                allowed = self._vision_support_map[rule_id]
                if not isinstance(allowed, set):
                    allowed = set(allowed) if allowed else set()
                matched_vision = [
                    s for s in vision_object_signals
                    if str((s.raw_data or {}).get("label", "")).strip().lower() in allowed
                ]
                if matched_vision:
                    for s in matched_vision:
                        signal_id = str(getattr(s, "signal_id", "unknown"))
                        evidence_data = _make_evidence_data(
                            "vision_object",
                            {
                                "label": (s.raw_data or {}).get("label"),
                                "confidence": 1.0,
                                "signal_confidence": getattr(s, "confidence", 0.8),
                                "bbox": (s.raw_data or {}).get("bbox"),
                                "model": (s.raw_data or {}).get("model", "grounding_dino"),
                            },
                            rule,
                        )
                        violations.append(
                            ViolationSchema(
                                signal_id=signal_id,
                                rule_id=rule_id,
                                violation_type="vision_object",
                                severity=severity_float,
                                evidence_data=evidence_data,
                            )
                        )

        return violations

    @staticmethod
    def _is_text_signal(s: Any) -> bool:
        if hasattr(s, "signal_type"):
            st = s.signal_type
            if st is not None:
                val = getattr(st, "value", str(st))
                if val == "text" or str(st).endswith("TEXT"):
                    return True
        rd = getattr(s, "raw_data", None) or {}
        return (
            rd.get("type") == "ocr_text"
            or rd.get("type") == "asr_text"
            or "text" in rd
        )

    @staticmethod
    def _embedding_by_regulation(signals: list[Any]) -> dict[str, list[Any]]:
        embedding_signals_by_regulation: dict[str, list[Any]] = {}
        for s in signals:
            if not hasattr(s, "raw_data") or (s.raw_data or {}).get("type") != "image_embedding_similarity":
                continue
            reg = (s.raw_data or {}).get("regulation")
            if reg:
                embedding_signals_by_regulation.setdefault(reg, []).append(s)
        return embedding_signals_by_regulation

    def _match_rule(
        self, text: str, rule_id: str, rule: dict
    ) -> DSLMatchResult | None:
        """Deterministic text match via DSL when compiled; else legacy matcher."""
        ast = self._rule_asts.get(rule_id)
        if ast is not None:
            return RuleEvaluator.evaluate(text, ast, original_text=text)
        return self._match_rule_legacy(text, rule)

    def _match_rule_legacy(self, text: str, rule: dict) -> DSLMatchResult | None:
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
                return DSLMatchResult(
                    matched_term=match.group(0),
                    confidence=confidence,
                    span={"start": match.start(), "end": match.end(), "text": match.group(0)},
                    match_kind="pattern",
                )
        for term in rule.get("prohibited_terms", []):
            term_lower = term.lower()
            if term_lower in text_lower:
                text_with_spaces = f" {text_lower} "
                conf = 0.95 if f" {term_lower} " in text_with_spaces else 0.85
                idx = text_lower.find(term_lower)
                return DSLMatchResult(
                    matched_term=term,
                    confidence=conf,
                    span={
                        "start": idx,
                        "end": idx + len(term_lower),
                        "text": text[idx : idx + len(term)] if idx >= 0 else term,
                    },
                    match_kind="term",
                )
        return None
