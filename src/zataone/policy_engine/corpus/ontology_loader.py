# zataone — load policy clauses from ontology/corpus YAML (sidecar to runtime rules)

from __future__ import annotations

import glob
import logging
import os
from pathlib import Path

import yaml

from zataone.policy_engine.corpus.models import PolicyClause, PolicyPack

logger = logging.getLogger(__name__)

# US platform + regulator corpus files used when jurisdiction is US.
_US_CORPUS_FILES = (
    "meta_ads_us.yaml",
    "google_ads_us.yaml",
    "tiktok_ads_us.yaml",
    "regulators_us.yaml",
)


def resolve_ontology_root() -> Path | None:
    """Return ontology/ directory (env override or repo-relative)."""
    env = (os.environ.get("ZATAONE_ONTOLOGY_PATH") or "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    # src/zataone/policy_engine/corpus/ontology_loader.py -> repo root
    here = Path(__file__).resolve()
    candidate = here.parents[4] / "ontology"
    if candidate.is_dir() and (candidate / "schema.yaml").is_file():
        return candidate
    return None


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _clause_rule_map(rules: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for rule in rules:
        rid = str(rule.get("id") or "")
        if not rid:
            continue
        for cid in rule.get("clause_ids") or []:
            out.setdefault(str(cid), []).append(rid)
    return out


def load_clauses_from_corpus_file(
    path: Path,
    *,
    jurisdiction: str = "US",
) -> list[PolicyClause]:
    """Parse one ontology corpus file into PolicyClause rows (active clauses only)."""
    doc = _load_yaml(path)
    j = jurisdiction.upper()
    clause_to_rules = _clause_rule_map(doc.get("rules") or [])
    clauses_out: list[PolicyClause] = []

    for cl in doc.get("clauses") or []:
        if not isinstance(cl, dict):
            continue
        if str(cl.get("status", "active")).lower() not in ("active",):
            continue
        juris = [str(x).upper() for x in (cl.get("jurisdiction") or ["US"])]
        if j not in juris and "GLOBAL" not in juris:
            continue
        cid = str(cl.get("id") or "")
        if not cid:
            continue
        text = str(cl.get("text") or "").strip()
        if not text:
            continue
        modalities = [str(m) for m in (cl.get("modalities") or ["text"])]
        tags = [str(cl.get("category_id") or "")]
        clauses_out.append(
            PolicyClause(
                clause_id=cid,
                text=text,
                modalities=modalities,
                rule_ids=list(clause_to_rules.get(cid, [])),
                tags=[t for t in tags if t],
            )
        )
    return clauses_out


def load_ontology_clauses(
    *,
    jurisdiction: str = "US",
    corpus_files: tuple[str, ...] | None = None,
    ontology_root: Path | None = None,
) -> list[PolicyClause]:
    """Load and dedupe clauses from selected ontology corpus files."""
    root = ontology_root or resolve_ontology_root()
    if root is None:
        logger.warning("ontology_loader: ontology root not found")
        return []

    corpus_dir = root / "corpus"
    if not corpus_dir.is_dir():
        return []

    files = corpus_files
    if files is None:
        j = jurisdiction.upper()
        if j == "US":
            files = _US_CORPUS_FILES
        else:
            files = tuple(
                os.path.basename(p)
                for p in sorted(glob.glob(str(corpus_dir / f"*_{j.lower()}.yaml")))
            )

    by_id: dict[str, PolicyClause] = {}
    for name in files:
        path = corpus_dir / name
        if not path.is_file():
            continue
        for clause in load_clauses_from_corpus_file(path, jurisdiction=jurisdiction):
            by_id[clause.clause_id] = clause

    return list(by_id.values())


def merge_ontology_clauses_into_pack(
    pack: PolicyPack,
    ontology_clauses: list[PolicyClause],
) -> PolicyPack:
    """
    Replace/add clauses on pack; keep runtime rules unchanged.
    Ontology clause text enriches BM25 retrieval and LLM policy_context.
    """
    if not ontology_clauses:
        return pack
    merged: dict[str, PolicyClause] = {c.clause_id: c for c in pack.clauses}
    for c in ontology_clauses:
        merged[c.clause_id] = c
    pack.clauses = sorted(merged.values(), key=lambda x: x.clause_id)
    return pack
