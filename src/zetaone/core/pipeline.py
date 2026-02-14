# zetaone core pipeline

"""
Domain-agnostic compliance pipeline.
Orchestrates extractors, policy evaluation, evidence, verdict, and persistence.
"""

import importlib
import logging
import os
import uuid
from typing import Any

from zetaone.extractors.registry import ExtractorRegistry
from zetaone.policy_engine.engine import PolicyEngine
from zetaone.storage.database import get_session_factory

logger = logging.getLogger(__name__)
from zetaone.services.audit_service import AuditService
from zetaone.services.evidence_service import EvidenceService
from zetaone.services.ingestion_service import IngestionService
from zetaone.services.signal_service import SignalService
from zetaone.services.verdict_service import VerdictService


class CompliancePipeline:
    """
    ZetaOne core compliance pipeline.
    Loads domain extractors and policies, orchestrates the full flow.
    """

    def __init__(self, domain: str):
        """
        Initialize pipeline for a domain.

        Args:
            domain: Domain name (e.g. "ad_compliance").
                   Loads extractors from zetaone.domains.<domain>.extractors
                   and policy pack from zetaone.domains.<domain>.policies
        """
        self._domain = domain
        self._extractor_registry = ExtractorRegistry()
        self._policy_engine = PolicyEngine()
        self._evidence_service = EvidenceService()
        self._verdict_service = VerdictService()
        self._ingestion_service = IngestionService()
        self._signal_service = SignalService()
        self._audit_service = AuditService()

        self._load_domain_extractors()
        self._load_domain_policies()

    def _load_domain_extractors(self) -> None:
        """Load and register extractors from domain module."""
        domain_module = importlib.import_module(f"zetaone.domains.{self._domain}")
        domain_path = os.path.dirname(domain_module.__file__)
        config = self._load_domain_config(domain_path)

        extractors_module = importlib.import_module(
            f"zetaone.domains.{self._domain}.extractors"
        )

        extractor_classes = []
        if hasattr(extractors_module, "OCRExtractor"):
            extractor_classes.append(("OCRExtractor", {}))
        if hasattr(extractors_module, "VisionExtractor"):
            vision_cfg = config.get("vision", {})
            extractor_classes.append(
                ("VisionExtractor", {"object_queries": vision_cfg.get("object_queries")})
            )
        if hasattr(extractors_module, "EmbeddingExtractor"):
            emb_cfg = config.get("embedding", {})
            reg_texts = [
                (k, v) for k, v in emb_cfg.get("regulation_texts", {}).items()
            ]
            extractor_classes.append(
                (
                    "EmbeddingExtractor",
                    {
                        "regulation_texts": reg_texts or None,
                        "similarity_threshold": emb_cfg.get("similarity_threshold", 0.6),
                    },
                )
            )
        if hasattr(extractors_module, "VLMExtractor"):
            extractor_classes.append(("VLMExtractor", {}))

        for name, kwargs in extractor_classes:
            cls = getattr(extractors_module, name)
            kwargs_clean = {k: v for k, v in kwargs.items() if v is not None}
            extractor = cls(**kwargs_clean)
            self._extractor_registry.register(extractor)

    def _load_domain_config(self, domain_path: str) -> dict:
        """Load domain config YAML if present."""
        import yaml

        config_path = os.path.join(domain_path, "configs", "meta_ads_config.yaml")
        if not os.path.exists(config_path):
            config_path = os.path.join(domain_path, "configs", f"{self._domain}_config.yaml")
        if not os.path.exists(config_path):
            return {}
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}

    def _load_domain_policies(self) -> None:
        """Load policy pack from domain policies."""
        domain_module = importlib.import_module(f"zetaone.domains.{self._domain}")
        domain_path = os.path.dirname(domain_module.__file__)

        import yaml

        policy_path = os.path.join(domain_path, "policies", "meta_ads.yaml")
        if not os.path.exists(policy_path):
            policy_path = os.path.join(domain_path, "policies", f"{self._domain}.yaml")
        if not os.path.exists(policy_path):
            return

        with open(policy_path, "r") as f:
            data = yaml.safe_load(f) or {}
        rules = data.get("rules", {})

        vision_support_map = {}
        embedding_rule_map = {}
        try:
            mappings_module = importlib.import_module(
                f"zetaone.domains.{self._domain}.mappings"
            )
            vision_support_map = getattr(mappings_module, "VISION_SUPPORT_MAP", {})
            embedding_rule_map = getattr(mappings_module, "EMBEDDING_RULE_MAP", {})
        except ImportError:
            pass

        self._policy_engine.load_policy_pack(
            rules=rules,
            vision_support_map=vision_support_map,
            embedding_rule_map=embedding_rule_map,
        )

    def run(
        self,
        asset: Any,
        tenant_id: uuid.UUID | str | None = None,
        persist: bool = True,
    ) -> dict:
        """
        Run the compliance pipeline on an asset.

        Args:
            asset: Asset with image_data (and domain-specific fields).
            tenant_id: Optional tenant ID for persistence. If None and persist=True,
                       uses default tenant.
            persist: If True, persist full compliance graph to database.

        Returns:
            Verdict dict with keys: verdict, risk_score, violations, signals,
            status, fix_suggestions, metadata.
        """
        signals = []
        for extractor in self._extractor_registry.list():
            try:
                extracted = extractor.extract(asset)
                if extracted:
                    signals.extend(extracted)
            except Exception:
                pass

        violations = self._policy_engine.evaluate(signals)

        evidence = self._evidence_service.generate(signals, violations)

        verdict = self._verdict_service.generate(evidence)

        if persist:
            self._persist_compliance_graph(
                asset=asset,
                signals=signals,
                evidence=evidence,
                verdict=verdict,
                tenant_id=tenant_id,
            )

        return verdict

    def _persist_compliance_graph(
        self,
        asset: Any,
        signals: list[Any],
        evidence: dict[str, Any],
        verdict: dict[str, Any],
        tenant_id: uuid.UUID | str | None,
    ) -> None:
        """Persist Asset → Signals → Evidence → Verdict → AuditEvent."""
        session = None
        try:
            SessionLocal = get_session_factory()
            session = SessionLocal()

            asset_record = self._ingestion_service.persist_asset(
                session, asset, tenant_id
            )

            signal_records = self._signal_service.persist_signals(
                session, asset_record.id, signals
            )

            self._evidence_service.persist_evidence(
                session, asset_record.id, signal_records, evidence
            )

            verdict_record = self._verdict_service.persist_verdict(
                session, asset_record.id, verdict
            )

            self._audit_service.persist_audit_event(
                session,
                asset_record.id,
                verdict_record.id,
                "COMPLIANCE_CHECK",
            )

            session.commit()
        except Exception as e:
            logger.exception("Persistence failed: %s", e)
        finally:
            if session is not None:
                session.close()
