# zataone — policy pack / clause context for advisory LLM

from __future__ import annotations

from typing import Any


def build_policy_context_for_llm(
    metadata: dict[str, Any] | None,
    *,
    max_clauses: int = 12,
    max_rule_snippets: int = 8,
    max_clause_chars: int = 1200,
    max_rule_chars: int = 500,
    vlm_inspection: str | None = None,
) -> dict[str, Any]:
    """
    Build compact policy corpus slice for advisory prompts.
    Uses BM25 retrieval metadata when present; otherwise all clauses (capped).
    """
    meta = metadata or {}
    pack = meta.get("policy_pack") or {}
    retrieval = meta.get("retrieval") or {}
    _ = vlm_inspection  # reserved; BM25 retrieval is stored on metadata by the pipeline

    pack_summary = {
        "id": pack.get("id"),
        "platform": pack.get("platform"),
        "jurisdiction": pack.get("jurisdiction"),
        "version": (pack.get("version") or {}).get("version") if isinstance(pack.get("version"), dict) else pack.get("version"),
        "rule_count": pack.get("rule_count"),
    }

    all_clauses = pack.get("clauses") or []
    retrieved_ids = set(retrieval.get("retrieved_clause_ids") or [])
    retrieved_rules = set(retrieval.get("retrieved_rule_ids") or [])

    clauses_out: list[dict[str, str]] = []
    if retrieved_ids:
        for c in all_clauses:
            if c.get("clause_id") in retrieved_ids:
                clauses_out.append(
                    {
                        "clause_id": c.get("clause_id", ""),
                        "text": (c.get("text") or "")[:max_clause_chars],
                        "rule_ids": c.get("rule_ids") or [],
                    }
                )
    if not clauses_out:
        for c in all_clauses[:max_clauses]:
            clauses_out.append(
                {
                    "clause_id": c.get("clause_id", ""),
                    "text": (c.get("text") or "")[:max_clause_chars],
                    "rule_ids": c.get("rule_ids") or [],
                }
            )

    rules = pack.get("rules") if isinstance(pack.get("rules"), dict) else {}
    rule_snippets: list[dict[str, str]] = []
    if isinstance(rules, dict):
        rule_ids = list(retrieved_rules) if retrieved_rules else list(rules.keys())[:max_rule_snippets]
        for rid in rule_ids[:max_rule_snippets]:
            r = rules.get(rid) or {}
            if isinstance(r, dict):
                rule_snippets.append(
                    {
                        "rule_id": rid,
                        "name": r.get("name", rid),
                        "description": (r.get("description") or "")[:max_rule_chars],
                    }
                )

    return {
        "policy_pack": pack_summary,
        "retrieval": {
            "method": retrieval.get("method"),
            "retrieved_rule_ids": list(retrieved_rules)[:max_rule_snippets],
            "retrieved_clause_ids": list(retrieved_ids)[:max_clauses],
            "retrieval_scores": retrieval.get("retrieval_scores") or {},
        },
        "clauses_for_review": clauses_out[:max_clauses],
        "rules_for_review": rule_snippets,
    }
