# zataone — build full PolicyPack from ontology/corpus (US default)

from __future__ import annotations

import glob
import logging
import os
from pathlib import Path

import yaml

from zataone.policy_engine.corpus.models import PolicyClause, PolicyPack, PolicyVersion
from zataone.policy_engine.corpus.ontology_loader import (
    load_clauses_from_corpus_file,
    resolve_ontology_root,
)
from zataone.policy_engine.corpus.ontology_platform import (
    clause_matches_platform,
    filter_rule_ids_for_platform,
    normalize_platform,
)
from zataone.policy_engine.corpus.ontology_rule_builder import ontology_rule_to_engine_rule

logger = logging.getLogger(__name__)


def list_us_corpus_files(ontology_root: Path) -> tuple[str, ...]:
    corpus_dir = ontology_root / "corpus"
    return tuple(
        sorted(os.path.basename(p) for p in glob.glob(str(corpus_dir / "*_us.yaml")))
    )


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_ontology_policy_pack(
    *,
    jurisdiction: str = "US",
    platform: str = "all",
    ontology_root: Path | None = None,
    corpus_files: tuple[str, ...] | None = None,
) -> PolicyPack | None:
    """
    Build PolicyPack from ontology US corpus: clauses + engine rules.
    Platform filter applied at build time (use platform='all' for full US pack).
    """
    root = ontology_root or resolve_ontology_root()
    if root is None:
        return None

    platform = normalize_platform(platform)
    corpus_dir = root / "corpus"
    files = corpus_files or list_us_corpus_files(root)
    eval_examples = _load_eval_examples(root)

    clauses_by_id: dict[str, PolicyClause] = {}
    clause_text_by_id: dict[str, str] = {}
    rules_engine: dict[str, dict] = {}

    for name in files:
        path = corpus_dir / name
        if not path.is_file():
            continue
        doc = _load_yaml(path)

        for cl in doc.get("clauses") or []:
            if str(cl.get("status", "active")).lower() != "active":
                continue
            cid = str(cl.get("id") or "")
            if not cid or not clause_matches_platform(cid, platform):
                continue
            juris = [str(x).upper() for x in (cl.get("jurisdiction") or ["US"])]
            if jurisdiction.upper() not in juris and "GLOBAL" not in juris:
                continue
            text = str(cl.get("text") or "").strip()
            if not text:
                continue
            clauses_by_id[cid] = PolicyClause(
                clause_id=cid,
                text=text,
                modalities=[str(m) for m in (cl.get("modalities") or ["text"])],
                rule_ids=[],
                tags=[str(cl.get("category_id") or "")],
            )
            clause_text_by_id[cid] = text

        for rule in doc.get("rules") or []:
            if str(rule.get("status", "active")).lower() != "active":
                continue
            clause_ids = [str(c) for c in (rule.get("clause_ids") or [])]
            clause_ids = [c for c in clause_ids if c in clauses_by_id]
            if not clause_ids:
                continue
            rid = str(rule.get("id") or "")
            if not rid:
                continue
            engine_key = rid
            texts = [clause_text_by_id.get(c, "") for c in clause_ids]
            vision_labels = _vision_labels_for_rule(rule, root)
            rules_engine[engine_key] = ontology_rule_to_engine_rule(
                rule,
                clause_texts=texts,
                eval_examples=eval_examples,
                vision_labels=vision_labels,
            )

        for engine_key, erule in rules_engine.items():
            for cid in erule.get("clause_ids") or []:
                if cid in clauses_by_id and engine_key not in clauses_by_id[cid].rule_ids:
                    clauses_by_id[cid].rule_ids.append(engine_key)

    clauses = sorted(clauses_by_id.values(), key=lambda c: c.clause_id)
    if not clauses or not rules_engine:
        logger.warning("ontology pack builder: empty clauses=%d rules=%d", len(clauses), len(rules_engine))
        return None

    return PolicyPack(
        id=f"ontology_{jurisdiction.lower()}_{platform}",
        platform=platform if platform != "all" else "multi",
        jurisdiction=jurisdiction.upper(),
        version=PolicyVersion(version="ontology", effective_date=None),
        modalities=["text", "image", "video", "audio", "landing_page"],
        clauses=clauses,
        rules=rules_engine,
        source_path=str(root / "corpus"),
    )


def _load_eval_examples(root: Path) -> list:
    path = root / "examples" / "eval_seed.yaml"
    if not path.is_file():
        return []
    data = yaml.safe_load(path.open(encoding="utf-8")) or {}
    return list(data.get("examples") or [])


def _vision_labels_for_rule(rule: dict, ontology_root: Path) -> list[str] | None:
    """Attach vision_primary_labels when rule/category is image-relevant."""
    try:
        from zataone.policy_engine.corpus.vision_queries import vision_labels_for_category
    except ImportError:
        return None
    modalities = rule.get("modalities") or []
    if "image" not in modalities and "video" not in modalities:
        cat = str(rule.get("category_id") or "")
        if cat not in ("gambling", "drugs", "alcohol", "health", "ip_trademark", "misleading"):
            return None
    labels = vision_labels_for_category(str(rule.get("category_id") or ""))
    return labels or None


def filter_pack_for_platform(pack: PolicyPack, platform: str) -> PolicyPack:
    """Return a shallow view: filtered clauses; rules restricted by platform."""
    platform = normalize_platform(platform)
    if platform == "all":
        return pack
    clauses = [c for c in pack.clauses if clause_matches_platform(c.clause_id, platform)]
    allowed_rules = filter_rule_ids_for_platform(pack.rules, platform) or set()
    rules = {k: v for k, v in pack.rules.items() if k in allowed_rules}
    filtered = PolicyPack(
        id=f"{pack.id}_{platform}",
        platform=platform,
        jurisdiction=pack.jurisdiction,
        version=pack.version,
        modalities=list(pack.modalities),
        clauses=clauses,
        rules=rules,
        source_path=pack.source_path,
    )
    return filtered
