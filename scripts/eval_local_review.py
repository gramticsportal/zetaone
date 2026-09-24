#!/usr/bin/env python3
"""Evaluate a self-hosted text reviewer on the same labeled rows scored by Gemini.

The baseline file is an existing end-to-end export whose ``display`` column came
from Gemini. This script reloads the corresponding human-labeled ontology examples,
runs the real Full pipeline with Ollama as the advisory provider, and reports both
systems against the human label. It therefore tests the integration we would ship,
including policy retrieval and structured-output validation.

Example:

    python scripts/eval_local_review.py \
      --baseline docs/_e2e_llm_vs_matcher_sample.json \
      --model qwen3:8b --limit 20 \
      --output docs/_local_review_qwen3_8b.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "ontology"))


def _is_positive(status: Any) -> bool:
    value = str(status or "").strip().upper()
    return value in {
        "NON_COMPLIANT",
        "LIKELY_REJECTED",
        "REVIEW_REQUIRED",
        "BORDERLINE",
    }


def _metrics(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    usable = [r for r in rows if r.get(field) and not r.get("error")]
    y = [r["label"] == "non_compliant" for r in usable]
    pred = [_is_positive(r[field]) for r in usable]
    tp = sum(a and b for a, b in zip(y, pred))
    fp = sum((not a) and b for a, b in zip(y, pred))
    fn = sum(a and (not b) for a, b in zip(y, pred))
    tn = sum((not a) and (not b) for a, b in zip(y, pred))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "n": len(usable),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round((tp + tn) / len(usable), 4) if usable else 0.0,
    }


def _high_severity_metrics(rows: list[dict[str, Any]], field: str) -> dict[str, Any]:
    high = [
        row
        for row in rows
        if row.get("label") == "non_compliant"
        and (
            row.get("deterministic_high_severity")
            or row.get("source") == "eval_precedents.yaml"
        )
        and row.get(field)
    ]
    false_negatives = sum(not _is_positive(row[field]) for row in high)
    return {
        "n": len(high),
        "false_negatives": false_negatives,
        "recall": round((len(high) - false_negatives) / len(high), 4) if high else None,
        "cohort": "HIGH/CRITICAL matcher hits plus enforcement precedents",
    }


def _review_fallback_reason(review: dict[str, Any], citation_valid: bool) -> str | None:
    agreement = str(review.get("agreement_with_deterministic") or "").strip().lower()
    if agreement == "unclear":
        return "model_unclear"
    if agreement == "diverges":
        return "model_diverges_from_deterministic"
    if not review.get("recommended_compliance_status") or not review.get(
        "recommended_verdict"
    ):
        return "missing_primary_verdict"
    if not citation_valid:
        return "invented_signal_citation"
    return None


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _select_rows(
    eval_rows: list[dict[str, Any]],
    baseline_rows: list[dict[str, Any]],
    *,
    limit: int,
    seed: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    by_id = {str(row.get("id")): row for row in eval_rows}
    joined = [
        (by_id[str(base.get("id"))], base)
        for base in baseline_rows
        if str(base.get("id")) in by_id
        and by_id[str(base.get("id"))].get("label") in {"compliant", "non_compliant"}
        and str(by_id[str(base.get("id"))].get("content") or "").strip()
    ]
    rng = random.Random(seed)
    positives = [pair for pair in joined if pair[0]["label"] == "non_compliant"]
    negatives = [pair for pair in joined if pair[0]["label"] == "compliant"]
    rng.shuffle(positives)
    rng.shuffle(negatives)
    pos_n = min(len(positives), (limit + 1) // 2)
    neg_n = min(len(negatives), limit - pos_n)
    selected = positives[:pos_n] + negatives[:neg_n]
    if len(selected) < limit:
        used = {pair[0]["id"] for pair in selected}
        remainder = [pair for pair in joined if pair[0]["id"] not in used]
        rng.shuffle(remainder)
        selected.extend(remainder[: limit - len(selected)])
    rng.shuffle(selected)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--model", default="qwen3:8b")
    parser.add_argument("--provider", choices=("ollama", "cascade"), default="cascade")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260922)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume rows already checkpointed in --output.",
    )
    parser.add_argument(
        "--retry-incomplete",
        action="store_true",
        help="With --resume, rerun missing reviews and rows affected by old citation metrics.",
    )
    args = parser.parse_args()

    os.environ["ZATAONE_REVIEW_PROVIDER"] = args.provider
    os.environ["OLLAMA_REVIEW_MODEL"] = args.model
    os.environ["ZATAONE_LLM_FINAL_REVIEW"] = "1"
    os.environ["ZATAONE_PIPELINE_ADVISORY"] = "1"
    os.environ["ZATAONE_VIRALITY_REVIEW"] = "0"
    os.environ["ZATAONE_HYBRID_NLP"] = "0"
    os.environ["ZATAONE_ENABLE_OCR"] = "0"
    os.environ["ZATAONE_ENABLE_VISION"] = "0"

    from examples.load_eval import load_eval_examples
    from zataone.core.pipeline import CompliancePipeline

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
    eval_rows = load_eval_examples(str(ROOT / "ontology"))
    selected = _select_rows(
        eval_rows,
        list(baseline.get("rows") or []),
        limit=max(1, args.limit),
        seed=args.seed,
    )
    if not selected:
        print("No baseline IDs matched labeled ontology examples.", file=sys.stderr)
        return 2

    pipeline = CompliancePipeline(domain="ad_compliance")
    results: list[dict[str, Any]] = []
    if args.resume and args.output and args.output.exists():
        prior = json.loads(args.output.read_text(encoding="utf-8"))
        results = list(prior.get("rows") or [])
    if args.retry_incomplete:
        results = [
            row
            for row in results
            if row.get("local_display")
            and not (row.get("cited_signal_ids") and not row.get("citation_valid"))
        ]
    completed_ids = {str(row.get("id")) for row in results}

    def build_report() -> dict[str, Any]:
        local_metrics = _metrics(results, "local_display")
        gemini_metrics = _metrics(results, "gemini_display")
        latencies = [
            float(r["model_latency_ms"])
            for r in results
            if isinstance(r.get("model_latency_ms"), (int, float))
        ]
        fallback_rows = [r for r in results if r.get("fallback_reason")]
        citation_rows = [
            r for r in results if r.get("schema_valid") and "citation_valid" in r
        ]
        return {
            "model": args.model,
            "provider": args.provider,
            "sample_size": len(results),
            "local": local_metrics,
            "gemini_baseline": gemini_metrics,
            "local_high_severity": _high_severity_metrics(results, "local_display"),
            "gemini_high_severity": _high_severity_metrics(results, "gemini_display"),
            "schema_valid_rate": round(
                sum(bool(r.get("schema_valid")) for r in results) / len(results), 4
            )
            if results
            else 0.0,
            "citation_valid_rate": round(
                sum(bool(r.get("citation_valid")) for r in citation_rows)
                / len(citation_rows),
                4,
            )
            if citation_rows
            else None,
            "estimated_fallback_rate": round(len(fallback_rows) / len(results), 4)
            if results
            else 0.0,
            "missing_reviews": sum(not r.get("local_display") for r in results),
            "errors": sum(bool(r.get("error")) for r in results),
            "latency_ms": {
                "median": round(statistics.median(latencies), 2) if latencies else None,
                "mean": round(statistics.fmean(latencies), 2) if latencies else None,
                "max": round(max(latencies), 2) if latencies else None,
            },
            "rows": results,
        }

    for index, (row, base) in enumerate(selected, 1):
        if str(row["id"]) in completed_ids:
            print(f"[{index:>3}/{len(selected)}] {row['id']}: resumed", flush=True)
            continue
        asset = SimpleNamespace(
            id=row["id"],
            content=str(row["content"]).strip(),
            type="text",
            image_data=None,
            metadata={},
        )
        started = time.perf_counter()
        result_row: dict[str, Any] = {
            "id": row["id"],
            "label": row["label"],
            "source": base.get("source"),
            "gemini_display": base.get("display"),
            "content_preview": str(row["content"])[:240],
        }
        try:
            verdict = pipeline.run(asset, persist=False, pipeline_mode="full")
            review = verdict.get("llm_final_review") or {}
            signal_ids: set[str] = set()
            for signal in verdict.get("signals") or []:
                value = (
                    signal.get("id") or signal.get("signal_id")
                    if isinstance(signal, dict)
                    else getattr(signal, "id", None)
                    or getattr(signal, "signal_id", None)
                )
                if value:
                    signal_ids.add(str(value))
            cited_ids = {
                str(signal_id)
                for signal_id in (review.get("cited_signal_ids") or [])
                if signal_id
            }
            citation_valid = not bool(cited_ids - signal_ids)
            severities: list[Any] = []
            for violation in verdict.get("violations") or []:
                value = (
                    violation.get("severity")
                    if isinstance(violation, dict)
                    else getattr(violation, "severity", None)
                )
                if value is not None:
                    severities.append(value)
            fallback_reason = _review_fallback_reason(review, citation_valid)
            result_row.update(
                {
                    "local_display": review.get("recommended_compliance_status"),
                    "local_verdict": review.get("recommended_verdict"),
                    "agreement": review.get("agreement_with_deterministic"),
                    "summary": review.get("summary"),
                    "provider": review.get("review_provider"),
                    "model": review.get("review_model"),
                    "model_latency_ms": review.get("review_latency_ms"),
                    "fallback_reason": review.get("review_fallback_reason")
                    or fallback_reason,
                    "fallback_unavailable": bool(review.get("review_fallback_unavailable")),
                    "schema_valid": bool(review.get("review_schema_valid")),
                    "citation_valid": citation_valid,
                    "cited_signal_ids": sorted(cited_ids),
                    "deterministic_high_severity": any(
                        (isinstance(value, (int, float)) and float(value) >= 0.7)
                        or str(value).upper() in {"HIGH", "CRITICAL"}
                        for value in severities
                    ),
                }
            )
        except Exception as exc:
            result_row["error"] = f"{type(exc).__name__}: {exc}"
        result_row["pipeline_latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        results.append(result_row)
        status = result_row.get("local_display") or result_row.get("error") or "missing"
        print(f"[{index:>3}/{len(selected)}] {row['id']}: {status}", flush=True)
        if args.output:
            _write_report(args.output, build_report())

    report = build_report()
    print("\n" + json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    if args.output:
        _write_report(args.output, report)
        print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
