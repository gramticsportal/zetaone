# zataone verdict service

import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from zataone.models import Verdict as VerdictModel


class VerdictService:
    """Verdict finalization, risk scoring, and persistence service."""

    # Spec-defined severity point values (0–100 scale).
    _SEVERITY_POINTS = {"CRITICAL": 100, "HIGH": 50, "MEDIUM": 20, "LOW": 5}
    # Confidence multipliers from spec.
    _CONF_HIGH = 1.0   # confidence > 0.9
    _CONF_MED  = 0.7   # confidence 0.7–0.9
    _CONF_LOW  = 0.3   # confidence < 0.7
    # Status / verdict thresholds on 0–100 scale.
    _NON_COMPLIANT_THRESHOLD = 70.0
    _BORDERLINE_THRESHOLD    = 30.0

    def __init__(self) -> None:
        # Legacy weights kept for _get_severity_value helper only.
        self._severity_weights = {
            "LOW": 0.2,
            "MEDIUM": 0.4,
            "HIGH": 0.7,
            "CRITICAL": 1.0,
        }

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
        *,
        tenant_id: uuid.UUID | str | None = None,
        policy_pack_id: str | None = None,
        processing_time_ms: int | None = None,
    ) -> VerdictModel:
        """Persist Verdict. Returns the persisted Verdict model."""
        result = self._sanitize_for_json(verdict_result)

        tid: uuid.UUID | None = None
        if tenant_id is not None:
            try:
                tid = uuid.UUID(str(tenant_id))
            except (ValueError, AttributeError):
                tid = None

        # Prefer explicit arg; fall back to timing in metadata.
        if processing_time_ms is None:
            timing = (verdict_result.get("metadata") or {}).get("pipeline_timing") or {}
            ms = timing.get("total_ms")
            if ms is not None:
                try:
                    processing_time_ms = int(ms)
                except (TypeError, ValueError):
                    pass

        model = VerdictModel(
            asset_id=asset_id,
            tenant_id=tid,
            policy_pack_id=policy_pack_id,
            status=verdict_result.get("status", ""),
            risk_score=float(verdict_result.get("risk_score", 0.0)),
            processing_time_ms=processing_time_ms,
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

    def _confidence_multiplier(self, confidence: float) -> float:
        """Spec: >0.9 → 1.0x, 0.7–0.9 → 0.7x, <0.7 → 0.3x."""
        if confidence > 0.9:
            return self._CONF_HIGH
        if confidence >= 0.7:
            return self._CONF_MED
        return self._CONF_LOW

    def _severity_points(self, severity_name: str) -> float:
        """Spec: CRITICAL=100, HIGH=50, MEDIUM=20, LOW=5."""
        return float(self._SEVERITY_POINTS.get(severity_name.upper(), 20))

    def _calculate_risk_score(self, violations: list[Any]) -> float:
        """
        Spec formula: SUM(severity_points × confidence_mult × jurisdiction_mult × history_mult),
        capped at 100. Jurisdiction and history default to 1.0 until those data points exist.
        Returns score on 0.0–100.0 scale.
        """
        if not violations:
            return 0.0

        total = 0.0
        for v in violations:
            severity_name = self._get_severity_value(v)
            points = self._severity_points(severity_name)

            # Extract the best available confidence value.
            if hasattr(v, "evidence_data"):
                ed = getattr(v, "evidence_data", {}) or {}
                raw_conf = ed.get("confidence") or ed.get("signal_confidence") or 0.8
            elif isinstance(v, dict):
                raw_conf = v.get("confidence", 0.8)
            else:
                raw_conf = getattr(v, "confidence", 0.8)
            try:
                conf = float(raw_conf)
            except (TypeError, ValueError):
                conf = 0.8

            conf_mult = self._confidence_multiplier(conf)
            # Jurisdiction and historical context multipliers — 1.0x until implemented.
            jurisdiction_mult = 1.0
            history_mult = 1.0

            total += points * conf_mult * jurisdiction_mult * history_mult

        return round(min(total, 100.0), 2)

    def _determine_status(self, risk_score: float, violations: list[Any]) -> str:
        if risk_score == 0.0:
            return "COMPLIANT"
        if risk_score >= self._NON_COMPLIANT_THRESHOLD:
            return "NON_COMPLIANT"
        return "REVIEW_REQUIRED"

    def _determine_verdict(self, risk_score: float) -> str:
        if risk_score >= self._NON_COMPLIANT_THRESHOLD:
            return "likely_rejected"
        if risk_score >= self._BORDERLINE_THRESHOLD:
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
