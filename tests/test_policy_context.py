"""Policy context builder for advisory LLM."""

import sys
from pathlib import Path

src = Path(__file__).resolve().parent.parent / "src"
if str(src) not in sys.path:
    sys.path.insert(0, str(src))

from zataone.core.policy_context import build_policy_context_for_llm


def test_build_policy_context_uses_retrieved_clauses():
    meta = {
        "policy_pack": {
            "id": "meta_ads",
            "platform": "meta",
            "jurisdiction": "US",
            "version": {"version": "1"},
            "rule_count": 2,
            "clauses": [
                {"clause_id": "c1", "text": "No false claims.", "rule_ids": ["r1"]},
                {"clause_id": "c2", "text": "Other clause.", "rule_ids": ["r2"]},
            ],
            "rules": {
                "r1": {"name": "False claims", "description": "Desc 1"},
                "r2": {"name": "Other", "description": "Desc 2"},
            },
        },
        "retrieval": {
            "method": "bm25",
            "retrieved_clause_ids": ["c1"],
            "retrieved_rule_ids": ["r1"],
            "retrieval_scores": {"r1": 1.5},
        },
    }
    ctx = build_policy_context_for_llm(meta)
    assert len(ctx["clauses_for_review"]) == 1
    assert ctx["clauses_for_review"][0]["clause_id"] == "c1"
    assert ctx["rules_for_review"][0]["rule_id"] == "r1"


def test_build_policy_context_caps_all_clauses_when_no_retrieval():
    clauses = [{"clause_id": f"c{i}", "text": f"t{i}", "rule_ids": []} for i in range(20)]
    meta = {"policy_pack": {"id": "p", "clauses": clauses}}
    ctx = build_policy_context_for_llm(meta, max_clauses=5)
    assert len(ctx["clauses_for_review"]) == 5
