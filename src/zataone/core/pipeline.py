# zataone core pipeline

"""
Domain-agnostic compliance pipeline.
Orchestrates extractors, policy evaluation, evidence, verdict, and persistence.
"""

from __future__ import annotations
import importlib
import logging
import os
import time
import uuid
from typing import Any

from zataone.core.extractor_flags import (
    embedding_enabled,
    fast_combined_review_enabled,
    pipeline_auto_advisory_enabled,
    pipeline_mode as default_pipeline_mode,
    pipeline_parallel_vlm_enabled,
    pipeline_vlm_extractor_enabled,
    semantic_text_enabled,
    policy_engine_enabled,
)
from zataone.core.verdict_display import apply_display_verdict
from zataone.core.extractor_plan import allow_domain_short_name, select_extractors_for_asset
from zataone.core.pipeline_progress import clear as progress_clear
from zataone.core.pipeline_progress import get as progress_get
from zataone.core.pipeline_progress import update as progress_update
from zataone.core.pipeline_run import (
    extract_signals_parallel,
    maybe_run_pipeline_advisory,
    run_parallel_vlm_and_deterministic,
)
from zataone.document.builder import DocumentBuilder
from zataone.document.flags import document_centric_enabled
from zataone.extractors.registry import ExtractorRegistry
from zataone.policy_engine.corpus.loader import load_policy_pack_from_dict
from zataone.policy_engine.jurisdiction.router import JurisdictionRouter
from zataone.policy_engine.engine import PolicyEngine
from zataone.policy_engine.retrieval.flags import policy_retrieval_enabled
from zataone.policy_engine.retrieval.retriever import PolicyRetriever
from zataone.storage.database import get_session_factory
from zataone.services.audit_service import AuditService
from zataone.services.evidence_service import EvidenceService
from zataone.services.ingestion_service import IngestionService
from zataone.services.signal_service import SignalService
from zataone.services.verdict_service import VerdictService
from zataone.services.violation_service import ViolationService

logger = logging.getLogger(__name__)


def resolve_pipeline_mode(mode: str | None = None) -> str:
    """Request header or env ZATAONE_PIPELINE_MODE (full|fast)."""
    if mode and str(mode).strip().lower() == "fast":
        return "fast"
    if mode and str(mode).strip().lower() == "full":
        return "full"
    return default_pipeline_mode()


def _enabled_domain_modalities(config: dict) -> set[str] | None:
    """
    If domain YAML lists extractors.enabled, only those short names are registered.
    Missing or empty list => all domain extractors that exist in the module.
    Short names: ocr, vision, embedding, vlm, asr
    """
    ex = config.get("extractors") or {}
    raw = ex.get("enabled")
    if raw is None:
        return None
    if isinstance(raw, list) and len(raw) == 0:
        return None
    return {str(x).strip().lower() for x in raw}


def _core_stub_extractors_disabled() -> bool:
    """When true, ad_compliance skips core OCR/Vision/Embedding/VLM (domain extractors only)."""
    v = os.environ.get("ZATAONE_DISABLE_CORE_STUB_EXTRACTORS", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if v in ("0", "false", "no", "off"):
        return False
    return False


class CompliancePipeline:
    """
    ZataOne core compliance pipeline.
    Loads domain extractors and policies, orchestrates the full flow.
    """

    def __init__(self, domain: str, jurisdiction: str = "US"):
        """
        Initialize pipeline for a domain + jurisdiction.

        Args:
            domain:      Domain name (e.g. "ad_compliance").
            jurisdiction: ISO-style jurisdiction code (US, EU, UK, CA, AU).
                         Selects the matching policy pack YAML; falls back to US.
        """
        self._domain = domain
        self._jurisdiction = JurisdictionRouter().normalize(jurisdiction)
        self._extractor_registry = ExtractorRegistry()
        self._policy_engine = PolicyEngine()
        self._policy_pack = None
        self._policy_retriever: PolicyRetriever | None = None
        self._evidence_service = EvidenceService()
        self._verdict_service = VerdictService()
        self._ingestion_service = IngestionService()
        self._signal_service = SignalService()
        self._violation_service = ViolationService()
        self._audit_service = AuditService()
        self._domain_config: dict = {}

        self._load_domain_extractors()
        self._load_domain_policies()

    def _load_domain_extractors(self) -> None:
        """Load and register extractors from domain module."""
        domain_module = importlib.import_module(f"zataone.domains.{self._domain}")
        domain_path = os.path.dirname(domain_module.__file__)
        config = self._load_domain_config(domain_path)
        self._domain_config = config

        extractors_module = importlib.import_module(
            f"zataone.domains.{self._domain}.extractors"
        )

        enabled = _enabled_domain_modalities(config)

        def _allow(short: str) -> bool:
            if not allow_domain_short_name(short, config):
                return False
            return enabled is None or short in enabled

        extractor_classes = []
        ocr_cfg = config.get("ocr") or {}
        if hasattr(extractors_module, "OCRExtractor") and _allow("ocr"):
            extractor_classes.append(
                (
                    "OCRExtractor",
                    {
                        "backend_type": ocr_cfg.get("backend", "tesseract"),
                        "min_confidence": ocr_cfg.get("min_confidence", 40),
                    },
                )
            )
        vision_cfg = config.get("vision", {})
        if hasattr(extractors_module, "VisionExtractor") and _allow("vision"):
            extractor_classes.append(
                (
                    "VisionExtractor",
                    {
                        "object_queries": vision_cfg.get("object_queries"),
                        "model_id": vision_cfg.get("model_id"),
                        "detection_threshold": vision_cfg.get("detection_threshold"),
                        "text_threshold": vision_cfg.get("text_threshold"),
                        "box_score_min": vision_cfg.get("box_score_min"),
                    },
                )
            )
        emb_cfg = config.get("embedding", {})
        if (
            hasattr(extractors_module, "EmbeddingExtractor")
            and _allow("embedding")
            and embedding_enabled()
        ):
            reg_texts = [
                (k, v) for k, v in emb_cfg.get("regulation_texts", {}).items()
            ]
            extractor_classes.append(
                (
                    "EmbeddingExtractor",
                    {
                        "regulation_texts": reg_texts or None,
                        "similarity_threshold": emb_cfg.get("similarity_threshold", 0.6),
                        "model_name": emb_cfg.get("model_name"),
                    },
                )
            )
        vlm_cfg = config.get("vlm") or {}
        if (
            hasattr(extractors_module, "VLMExtractor")
            and _allow("vlm")
            and pipeline_vlm_extractor_enabled()
        ):
            extractor_classes.append(
                (
                    "VLMExtractor",
                    {
                        "model": vlm_cfg.get("model"),
                        "max_tokens": vlm_cfg.get("max_tokens"),
                        "temperature": vlm_cfg.get("temperature"),
                        "env_api_key": vlm_cfg.get("env_api_key"),
                    },
                )
            )
        if hasattr(extractors_module, "AsrExtractor") and _allow("asr"):
            extractor_classes.append(("AsrExtractor", {}))

        # Core extractors for ad_compliance (text + video always; OCR/Vision/Embedding/VLM optional)
        if self._domain == "ad_compliance":
            from zataone.extractors.text_extractor import TextExtractor
            from zataone.extractors.video_extractor import VideoExtractor
            from zataone.extractors.ocr_extractor import OCRExtractor
            from zataone.extractors.vision_extractor import VisionExtractor
            from zataone.extractors.embedding_extractor import EmbeddingExtractor
            from zataone.extractors.vlm_extractor import VLMExtractor

            self._extractor_registry.register(TextExtractor())
            self._extractor_registry.register(VideoExtractor())
            if semantic_text_enabled():
                from zataone.extractors.semantic_text_extractor import SemanticTextExtractor

                self._extractor_registry.register(SemanticTextExtractor())
            if _core_stub_extractors_disabled():
                logger.info(
                    "Core stub extractors disabled (ZATAONE_DISABLE_CORE_STUB_EXTRACTORS); "
                    "using domain OCR/Vision/Embedding/VLM only."
                )
            else:
                self._extractor_registry.register(OCRExtractor())
                self._extractor_registry.register(VisionExtractor())
                if embedding_enabled():
                    self._extractor_registry.register(EmbeddingExtractor())
                if pipeline_vlm_extractor_enabled():
                    self._extractor_registry.register(VLMExtractor())

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
        """Load jurisdiction-appropriate policy pack from domain policies."""
        domain_module = importlib.import_module(f"zataone.domains.{self._domain}")
        domain_path = os.path.dirname(domain_module.__file__)

        import yaml

        policy_path = JurisdictionRouter().resolve_policy_path(
            domain_path, self._domain, self._jurisdiction
        )
        if not policy_path:
            return

        logger.info(
            "Loading policy pack: %s (domain=%s, jurisdiction=%s)",
            os.path.basename(policy_path), self._domain, self._jurisdiction,
        )

        with open(policy_path, "rb") as f:
            raw = f.read()
        data = yaml.safe_load(raw) or {}

        self._policy_pack = load_policy_pack_from_dict(
            data,
            source_path=policy_path,
            jurisdiction=self._jurisdiction,
        )
        import hashlib

        self._policy_pack.content_hash = hashlib.sha256(raw).hexdigest()
        rules = self._policy_pack.rules

        vision_support_map = {}
        embedding_rule_map = {}
        try:
            mappings_module = importlib.import_module(
                f"zataone.domains.{self._domain}.mappings"
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
        self._policy_retriever = PolicyRetriever(self._policy_pack)

    def _run_fast_precore(
        self,
        asset: Any,
        *,
        asset_id: str | None = None,
        run_mode: str = "fast",
        vlm_inspection: str | None = None,
    ) -> dict[str, Any]:
        """Quick mode: no extractors / no rule engine; placeholder until LLM assessment."""
        t0 = time.perf_counter()
        if asset_id:
            progress_update(asset_id, extraction="skipped", signal_count=0)

        signals: list[Any] = []
        document = DocumentBuilder.build(asset, signals)
        if not document.normalized_text and getattr(asset, "content", None):
            document.normalized_text = str(asset.content)[:50000]
        if not document.normalized_text and vlm_inspection:
            document.normalized_text = str(vlm_inspection)[:8000]
        document.metadata["document_centric_enabled"] = document_centric_enabled()
        document.metadata["pipeline_mode"] = run_mode

        retrieval_result = None

        violations: list[Any] = []
        evidence = self._evidence_service.generate(signals, violations)
        verdict = self._verdict_service.generate(evidence)
        verdict["status"] = "PENDING_ADVISORY"
        verdict["verdict"] = "pending_advisory"

        verdict_metadata = dict(verdict.get("metadata") or {})
        verdict_metadata["document"] = document.to_dict()
        verdict_metadata["document_centric_enabled"] = document_centric_enabled()
        verdict_metadata["pipeline_mode"] = run_mode
        verdict_metadata["fast_mode_no_extractors"] = True
        verdict_metadata["policy_engine_ran"] = False
        verdict_metadata["policy_engine_enabled"] = False
        verdict_metadata["verdict_authority"] = "advisory"
        if self._policy_pack is not None:
            verdict_metadata["policy_pack"] = self._policy_pack.to_dict()
        if retrieval_result is not None:
            verdict_metadata["retrieval"] = retrieval_result.to_dict()
        verdict_metadata["policy_retrieval_enabled"] = policy_retrieval_enabled()
        verdict["metadata"] = verdict_metadata

        return {
            "verdict": verdict,
            "signals": signals,
            "violations_raw": violations,
            "evidence": evidence,
            "extractor_counts": {},
            "timing_ms": {"fast_precore_ms": round((time.perf_counter() - t0) * 1000)},
        }

    def _run_deterministic_core(
        self,
        asset: Any,
        *,
        asset_id: str | None = None,
        run_pipeline_mode: str = "full",
    ) -> dict[str, Any]:
        """Extraction → document → policy → evidence → verdict (no advisory)."""
        t0 = time.perf_counter()
        extractors = select_extractors_for_asset(
            self._extractor_registry.list(),
            asset,
            self._domain_config,
            run_pipeline_mode=run_pipeline_mode,
        )
        signals, counts, failed_extractors = extract_signals_parallel(
            extractors, asset, asset_id=asset_id
        )

        producers = sorted(eid for eid, n in counts.items() if n > 0)
        logger.info(
            "Extraction complete: total_signals=%d counts=%s producers=%s",
            len(signals),
            counts,
            producers,
        )

        document = DocumentBuilder.build(asset, signals)
        document.metadata["document_centric_enabled"] = document_centric_enabled()
        logger.info(
            "Document built: modality=%s chars=%d spans=%d scenes=%d",
            document.modality,
            len(document.normalized_text),
            len(document.spans),
            len(document.scene_descriptions),
        )

        evaluate_document = document if document_centric_enabled() else None

        retrieval_result = None
        active_rule_ids = None
        if self._policy_retriever is not None:
            vision_primary_ids = {
                rid
                for rid, rule in (self._policy_pack.rules if self._policy_pack else {}).items()
                if rule.get("vision_primary_labels")
            }
            retrieval_result = self._policy_retriever.retrieve(
                document.normalized_text,
                vision_rule_ids=vision_primary_ids,
            )
            if policy_retrieval_enabled() and retrieval_result.retrieved_rule_ids:
                active_rule_ids = set(retrieval_result.retrieved_rule_ids)

        engine_on = policy_engine_enabled()
        if engine_on:
            violations = self._policy_engine.evaluate(
                signals, document=evaluate_document, active_rule_ids=active_rule_ids
            )
        else:
            violations = []

        evidence = self._evidence_service.generate(signals, violations)
        verdict = self._verdict_service.generate(evidence)
        if not engine_on:
            verdict["status"] = "PENDING_ADVISORY"
            verdict["verdict"] = "pending_advisory"

        # Fail to review, never to approve: a crashed extractor means coverage
        # is incomplete, so a clean result cannot be trusted as COMPLIANT.
        if failed_extractors:
            logger.warning(
                "Extraction degraded (%s); capping verdict at REVIEW_REQUIRED",
                sorted(failed_extractors),
            )
            if verdict.get("status") == "COMPLIANT":
                verdict["status"] = "REVIEW_REQUIRED"
            if verdict.get("verdict") == "likely_approved":
                verdict["verdict"] = "borderline"

        verdict_metadata = dict(verdict.get("metadata") or {})
        if failed_extractors:
            verdict_metadata["degraded_extractors"] = failed_extractors
        verdict_metadata["document"] = document.to_dict()
        verdict_metadata["document_centric_enabled"] = document_centric_enabled()
        if self._policy_pack is not None:
            verdict_metadata["policy_pack"] = self._policy_pack.to_dict()
        if retrieval_result is not None:
            verdict_metadata["retrieval"] = retrieval_result.to_dict()
        verdict_metadata["policy_retrieval_enabled"] = policy_retrieval_enabled()
        verdict_metadata["pipeline_mode"] = run_pipeline_mode
        verdict_metadata["policy_engine_ran"] = engine_on
        verdict_metadata["policy_engine_enabled"] = engine_on
        verdict_metadata["verdict_authority"] = "deterministic" if engine_on else "advisory"
        verdict["metadata"] = verdict_metadata

        return {
            "verdict": verdict,
            "signals": signals,
            "violations_raw": violations,
            "evidence": evidence,
            "extractor_counts": counts,
            "timing_ms": {"deterministic_core_ms": round((time.perf_counter() - t0) * 1000)},
        }

    def run(
        self,
        asset: Any,
        tenant_id: uuid.UUID | str | None = None,
        persist: bool = True,
        idempotency_key: str | None = None,
        existing_asset_id: uuid.UUID | None = None,
        pipeline_mode: str | None = None,
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
        start_time = time.perf_counter()
        mode = resolve_pipeline_mode(pipeline_mode)
        aid_str = str(existing_asset_id) if existing_asset_id else None
        if aid_str:
            progress_clear(aid_str)
            progress_update(aid_str, status="processing", pipeline_mode=mode)

        image_bytes = getattr(asset, "image_data", None)
        asset_type = getattr(asset, "type", None) or "text"
        parallel_timing: dict[str, Any] = {}
        vlm_status: dict[str, Any] | None = None

        if mode == "fast":
            det_bundle = self._run_fast_precore(asset, asset_id=aid_str, run_mode=mode)
            use_combined = (
                fast_combined_review_enabled()
                and asset_type == "image"
                and bool(image_bytes)
                and pipeline_auto_advisory_enabled()
            )
            if use_combined:
                from zataone.services.llm_final_review_service import run_fast_combined_image_review

                if aid_str:
                    progress_update(aid_str, vlm="running", advisory="running")
                t_fast = time.perf_counter()
                try:
                    stored, vlm_status = run_fast_combined_image_review(
                        image_bytes,
                        domain=self._domain,
                        verdict=det_bundle["verdict"],
                    )
                    det_bundle["verdict"]["llm_final_review"] = stored
                    meta = det_bundle["verdict"].setdefault("metadata", {})
                    meta["advisory_vlm"] = vlm_status
                    meta["fast_combined_review"] = True
                    meta["pipeline_advisory"] = True
                    parallel_timing["fast_combined_ms"] = round(
                        (time.perf_counter() - t_fast) * 1000
                    )
                    if aid_str:
                        progress_update(aid_str, vlm="completed", advisory="completed")
                except Exception:
                    logger.exception("Fast combined review failed; falling back to VLM+LLM")
                    use_combined = False
                    if aid_str:
                        progress_update(aid_str, advisory="skipped")

            if not use_combined:
                inspection: str | None = None
                run_vlm = (
                    pipeline_parallel_vlm_enabled()
                    and asset_type == "image"
                    and bool(image_bytes)
                    and pipeline_auto_advisory_enabled()
                )
                if run_vlm:
                    from zataone.services.llm_final_review_service import run_gemini_vlm_inspection

                    if aid_str:
                        progress_update(aid_str, vlm="running")
                    t_vlm = time.perf_counter()
                    vlm_summary, vlm_error, vlm_status = run_gemini_vlm_inspection(
                        image_bytes,
                        domain=self._domain,
                        det={"status": "PROCESSING", "verdict": "pending", "risk_score": None},
                    )
                    parallel_timing["vlm_ms"] = round((time.perf_counter() - t_vlm) * 1000)
                    inspection = vlm_summary
                    if aid_str:
                        progress_update(
                            aid_str,
                            vlm="completed" if (vlm_status or {}).get("vlm_succeeded") else "failed",
                            vlm_error=vlm_error,
                        )
                elif aid_str:
                    progress_update(aid_str, vlm="skipped", vlm_skipped_reason="not_image_or_no_key")
                if inspection:
                    doc = (det_bundle["verdict"].get("metadata") or {}).get("document") or {}
                    if isinstance(doc, dict) and not doc.get("normalized_text"):
                        doc["normalized_text"] = str(inspection)[:8000]

            if aid_str:
                progress_update(aid_str, deterministic="completed")
        else:

            def _deterministic_core() -> dict[str, Any]:
                return self._run_deterministic_core(
                    asset, asset_id=aid_str, run_pipeline_mode=mode
                )

            det_bundle, vlm_status, parallel_timing = run_parallel_vlm_and_deterministic(
                asset=asset,
                image_bytes=image_bytes,
                domain=self._domain,
                asset_id=aid_str,
                deterministic_fn=_deterministic_core,
            )

        verdict = det_bundle["verdict"]
        signals = det_bundle["signals"]
        evidence = det_bundle["evidence"]
        counts = det_bundle.get("extractor_counts") or {}

        if not (det_bundle["verdict"].get("metadata") or {}).get("fast_combined_review"):
            maybe_run_pipeline_advisory(
                domain=self._domain,
                asset=asset,
                asset_id=aid_str,
                det_bundle=det_bundle,
                vlm_status=vlm_status,
                image_bytes=image_bytes,
            )

        engine_ran = bool((verdict.get("metadata") or {}).get("policy_engine_ran"))
        apply_display_verdict(
            verdict,
            signal_count=len(signals),
            pipeline_mode=mode,
            policy_engine_ran=engine_ran,
        )

        verdict_metadata = dict(verdict.get("metadata") or {})
        verdict_metadata["pipeline_mode"] = mode
        verdict_metadata["pipeline_timing"] = {
            **det_bundle.get("timing_ms", {}),
            **parallel_timing,
            "total_ms": round((time.perf_counter() - start_time) * 1000),
        }
        verdict_metadata["extractor_counts"] = counts
        verdict_metadata["embedding_enabled"] = embedding_enabled()
        verdict_metadata["pipeline_vlm_extractor_enabled"] = pipeline_vlm_extractor_enabled()
        if aid_str:
            verdict_metadata["pipeline_progress"] = progress_get(aid_str) or {}
            progress_update(aid_str, status="completed")
        verdict["metadata"] = verdict_metadata

        asset_id_result: uuid.UUID | None = existing_asset_id
        if persist:
            asset_id_result = self._persist_compliance_graph(
                asset=asset,
                signals=signals,
                evidence=evidence,
                verdict=verdict,
                tenant_id=tenant_id,
                idempotency_key=idempotency_key,
                existing_asset_id=existing_asset_id,
            )

        if persist and existing_asset_id is not None and asset_id_result is None:
            sess = get_session_factory()()
            try:
                self._ingestion_service.set_asset_status(sess, existing_asset_id, "failed")
            except Exception:
                logger.exception(
                    "Could not mark asset %s failed after persistence error",
                    existing_asset_id,
                )
            finally:
                sess.close()

        processing_time_ms = round((time.perf_counter() - start_time) * 1000)
        tenant_id_str = str(tenant_id) if tenant_id is not None else None
        logger.info(
            "Pipeline completed",
            extra={
                "asset_id": str(asset_id_result) if asset_id_result else None,
                "tenant_id": tenant_id_str,
                "verdict": verdict.get("verdict", ""),
                "risk_score": verdict.get("risk_score", 0.0),
                "processing_time_ms": processing_time_ms,
            },
        )
        return verdict

    def _persist_compliance_graph(
        self,
        asset: Any,
        signals: list[Any],
        evidence: dict[str, Any],
        verdict: dict[str, Any],
        tenant_id: uuid.UUID | str | None,
        idempotency_key: str | None = None,
        existing_asset_id: uuid.UUID | None = None,
    ) -> uuid.UUID | None:
        """
        Persist full compliance graph. Single shared session, atomic transaction.
        Order: 1) asset 2) signals 3) violations 4) evidence 5) verdict 6) audit event.
        Returns asset_id.
        """
        session = None
        try:
            SessionLocal = get_session_factory()
            session = SessionLocal()

            if existing_asset_id is not None:
                from zataone.models import Asset as AssetModel
                from zataone.services.ingestion_service import compute_content_hash

                asset_record = session.query(AssetModel).filter(
                    AssetModel.id == existing_asset_id
                ).first()
                if asset_record is None:
                    logger.error("Existing asset %s not found", existing_asset_id)
                    return None
                asset_record.status = "completed"
                asset_record.content_hash = compute_content_hash(asset)
                session.flush()
            else:
                asset_record = self._ingestion_service.persist_asset(
                    session, asset, tenant_id, idempotency_key=idempotency_key
                )

            signal_records = self._signal_service.persist_signals(
                session, asset_record.id, signals
            )

            violation_records = self._violation_service.persist_violations(
                session, asset_record.id, signal_records, evidence.get("violations", [])
            )

            self._evidence_service.persist_evidence(
                session, asset_record.id, signal_records, violation_records
            )

            policy_pack_id: str | None = None
            if self._policy_pack is not None:
                pp = self._policy_pack
                policy_pack_id = getattr(pp, "pack_id", None) or getattr(pp, "name", None)

            verdict_record = self._verdict_service.persist_verdict(
                session,
                asset_record.id,
                verdict,
                tenant_id=tenant_id,
                policy_pack_id=policy_pack_id,
            )

            # Queue borderline / flagged / degraded outcomes for human review.
            from zataone.services.review_service import review_state_for_verdict

            asset_record.review_state = review_state_for_verdict(verdict)

            self._audit_service.persist_audit_event(
                session,
                asset_record.id,
                verdict_record.id,
                "COMPLIANCE_CHECK",
                tenant_id=tenant_id,
                action="COMPLIANCE_CHECK",
                after_state={
                    "status": verdict.get("status"),
                    "risk_score": verdict.get("risk_score"),
                    "verdict": verdict.get("verdict"),
                },
            )

            session.commit()

            # Fire webhooks after successful commit (non-blocking, daemon thread).
            try:
                from zataone.services.webhook_service import WebhookService
                verdict_status = verdict.get("status", "")
                event_type = (
                    "verdict.flagged"
                    if verdict_status in ("NON_COMPLIANT", "BORDERLINE")
                    else "verdict.completed"
                )
                WebhookService().fire_event_async(
                    event_type,
                    {
                        "asset_id": str(asset_record.id),
                        "verdict": verdict_status,
                        "risk_score": verdict.get("risk_score"),
                        "policy_pack_id": policy_pack_id,
                    },
                    tenant_id=tenant_id,
                )
            except Exception:
                pass  # webhook errors must never abort the pipeline

            return asset_record.id
        except Exception as e:
            if session is not None:
                session.rollback()
            logger.exception("Persistence failed: %s", e)
            return None
        finally:
            if session is not None:
                session.close()
