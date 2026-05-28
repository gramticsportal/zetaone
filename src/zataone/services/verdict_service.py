# zataone verdict service

from __future__ import annotations
import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from zataone.models import Verdict as VerdictModel


class VerdictService:
    """Verdict finalization, risk scoring, and persistence service."""

    def __init__(self) -> None:
        self._severity_weights = {
            "LOW": 0.2,
            "MEDIUM": 0.4,
            "HIGH": 0.7,
            "CRITICAL": 1.0,
        }
        self._verdict_threshold = 0.7
        self._count_factor = 0.03
        self._severity_factor_critical = 0.2
        self._severity_factor_high = 0.1

    def generate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        """
        Generate verdict from evidence bundle.

        Args:
            evidence: Dict with keys "signals", "violations".

        Returns:
            Verdict dict with verdict, risk_score, violations, signals,
            status, fix_suggestions, metadata.
        """
        violations = evidence.get("violations", [])
        signals = evidence.get("signals", [])

        risk_score = self._calculate_risk_score(violations)
        status = self._determine_status(risk_score, violations)
        verdict = self._determine_verdict(risk_score)
        fix_suggestions = self._generate_fix_suggestions(violations)

        return {
            "verdict": verdict,
            "risk_score": risk_score,
            "violations": violations,
            "signals": signals,
            "status": status,
            "fix_suggestions": fix_suggestions,
            "metadata": {},
        }

    def _sanitize_for_json(self, obj: Any) -> Any:
        """Convert object to JSON-serializable form (dataclasses, Enums, dates, ORM leftovers)."""
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, type) and issubclass(obj, Enum):
            return obj.__name__
        if isinstance(obj, dict):
            return {str(k): self._sanitize_for_json(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple, set)):
            return [self._sanitize_for_json(v) for v in obj]
        if hasattr(obj, "item") and callable(getattr(obj, "item")):
            try:
                return self._sanitize_for_json(obj.item())
            except Exception:
                pass
        if hasattr(obj, "tolist") and callable(getattr(obj, "tolist")):
            try:
                return self._sanitize_for_json(obj.tolist())
            except Exception:
                pass
        if hasattr(obj, "__dict__") and not isinstance(obj, type):
            try:
                return self._sanitize_for_json(vars(obj))
            except TypeError:
                pass
        return str(obj)

    def persist_verdict(
        self,
        session: Session,
        asset_id: uuid.UUID,
        verdict_result: dict[str, Any],
    ) -> VerdictModel:
        """Persist Verdict. Returns the persisted Verdict model."""
        result = self._sanitize_for_json(verdict_result)
        model = VerdictModel(
            asset_id=asset_id,
            status=verdict_result.get("status", ""),
            risk_score=float(verdict_result.get("risk_score", 0.0)),
            result=result,
        )
        session.add(model)
        session.flush()
        return model

    def _get_severity_value(self, v: Any) -> str:
        if hasattr(v, "severity"):
            sv = v.severity
            if isinstance(sv, (int, float)):
                for name, val in self._severity_weights.items():
                    if abs(val - sv) < 0.01:
                        return name
                return "HIGH" if sv >= 0.7 else "MEDIUM" if sv >= 0.4 else "LOW"
            return sv.value if hasattr(sv, "value") else str(sv)
        return str(v.get("severity", "HIGH"))

    def _calculate_risk_score(self, violations: list[Any]) -> float:
        if not violations:
            return 0.0
        total_weighted_risk = 0.0
        total_weight = 0.0
        for v in violations:
            if hasattr(v, "evidence_data"):
                ed = getattr(v, "evidence_data", {})
                avg_conf = ed.get("confidence", 0.8) * ed.get("signal_confidence", 0.8)
                base_risk = getattr(v, "severity", 0.5)
                if not isinstance(base_risk, (int, float)):
                    base_risk = self._severity_weights.get(self._get_severity_value(v), 0.5)
            else:
                evidence_list = (
                    v.get("evidence", []) if isinstance(v, dict) else getattr(v, "evidence", [])
                )
                if evidence_list:
                    def _ev_data(e):
                        return e.data if hasattr(e, "data") else e.get("data", {})

                    avg_conf = sum(
                        _ev_data(e).get("confidence", 0.8)
                        * _ev_data(e).get("signal_confidence", 0.8)
                        for e in evidence_list
                    ) / len(evidence_list)
                else:
                    avg_conf = 0.8
                base_risk = self._severity_weights.get(self._get_severity_value(v), 0.5)
            total_weighted_risk += base_risk * avg_conf
            total_weight += avg_conf
        base_score = total_weighted_risk / total_weight if total_weight > 0 else 0.5
        count_factor = min(len(violations) * self._count_factor, 0.15)
        severities = [self._get_severity_value(v) for v in violations]
        has_critical = "CRITICAL" in severities
        has_high = "HIGH" in severities
        severity_factor = (
            self._severity_factor_critical
            if has_critical
            else self._severity_factor_high if has_high else 0.0
        )
        return round(min(base_score + count_factor + severity_factor, 1.0), 3)

    def _determine_status(self, risk_score: float, violations: list[Any]) -> str:
        if risk_score == 0.0:
            return "COMPLIANT"
        if risk_score >= 0.7:
            return "NON_COMPLIANT"
        return "REVIEW_REQUIRED"

    def _determine_verdict(self, risk_score: float) -> str:
        if risk_score > self._verdict_threshold:
            return "likely_rejected"
        if risk_score >= 0.3:
            return "borderline"
        return "likely_approved"

    def _generate_fix_suggestions(self, violations: list[Any]) -> list[str]:
        suggestions = []
        seen_rules = set()
        for v in violations:
            rule_id = (
                v.get("rule_id", "") if isinstance(v, dict) else getattr(v, "rule_id", "")
            )
            if rule_id in seen_rules:
                continue
            seen_rules.add(rule_id)
            if hasattr(v, "evidence_data"):
                rule_name = getattr(v, "evidence_data", {}).get("rule_name", "")
                severity = self._get_severity_value(v)
                evidence_list = [v]  # single evidence in evidence_data
            else:
                rule_name = (
                    v.get("rule_name", "") if isinstance(v, dict) else getattr(v, "rule_name", "")
                )
                severity = self._get_severity_value(v)
                evidence_list = (
                    v.get("evidence", []) if isinstance(v, dict) else getattr(v, "evidence", [])
                )
            if rule_id == "misleading_exaggerated_claims":
                matched_terms = set()
                for e in evidence_list:
                    if hasattr(e, "evidence_data"):
                        data = getattr(e, "evidence_data", {})
                    else:
                        data = e.data if hasattr(e, "data") else e.get("data", {})
                    term = data.get("matched_term", "")
                    if term:
                        matched_terms.add(term.lower())
                if matched_terms:
                    terms_list = ", ".join(sorted(matched_terms))
                    suggestions.append(
                        f"Remove or rephrase misleading claims: {terms_list}. "
                        "Replace absolute guarantees with qualified statements."
                    )
            elif rule_id in ("biopharma_prohibited_claims", "finance_prohibited_claims"):
                suggestions.append(
                    "Remove medical/financial guarantees. "
                    "Use qualified language and include disclaimers."
                )
            sev_val = getattr(v, "severity", None)
            is_high = severity in ("HIGH", "CRITICAL") or (
                isinstance(sev_val, (int, float)) and sev_val >= 0.7
            )
            if is_high:
                suggestions.append(
                    f"Review and revise content to address {(rule_name or rule_id).lower()}. "
                    "Ensure all claims are substantiated and comply with advertising guidelines."
                )
        seen = set()
        unique = [s for s in suggestions if s not in seen and not seen.add(s)]
        return unique[:5]
