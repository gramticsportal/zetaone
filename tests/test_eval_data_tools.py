"""Eval-data tooling: disagreement queue, agreement study, annotations, quality report."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ontology" / "tools"))
sys.path.insert(0, str(ROOT / "ontology"))

import agreement_study  # noqa: E402
import build_disagreement_queue as queue_mod  # noqa: E402
import data_quality_report  # noqa: E402
import validate_annotations  # noqa: E402


def _run_row(row_id, label, matcher, local, gemini=None):
    return {
        "id": row_id,
        "label": label,
        "source": "eval_harvested.yaml",
        "matcher_display": matcher,
        "local_display": local,
        "gemini_display": gemini,
    }


def test_queue_ranks_unanimous_disagreement_and_flags_hazards():
    examples = {
        "a": {"content": "Buy One Get One", "labeled_by": "model", "category_ids": ["misleading"]},
        "b": {"content": "A long enough violation sentence here.", "labeled_by": "expert"},
        "c": {
            "content": "Looks plumped for many users",
            "labeled_by": "model",
            "note": "compliant minimal pair of x; technique: qualification_added",
        },
        "d": {"content": "Agreed row", "labeled_by": "model"},
    }
    rows = [
        _run_row("b", "non_compliant", "COMPLIANT", "COMPLIANT"),
        _run_row("a", "non_compliant", "COMPLIANT", "COMPLIANT"),
        _run_row("c", "compliant", "NON_COMPLIANT", "REVIEW_REQUIRED"),
        _run_row("d", "non_compliant", "NON_COMPLIANT", "LIKELY_REJECTED"),
    ]
    queue = queue_mod.build_queue(rows, examples)

    assert [q["id"] for q in queue] == ["a", "c", "b"]
    assert queue[0]["flags"] == "fragment"
    assert queue[1]["flags"] == "hedge_only_pair"
    assert queue[1]["error_type"] == "FP"
    assert all(q["priority"] == "high" for q in queue)


def test_queue_uses_majority_when_gemini_scored():
    rows = [_run_row("x", "compliant", "NON_COMPLIANT", "COMPLIANT", "LIKELY_REJECTED")]
    queue = queue_mod.build_queue(rows, {"x": {"content": "An ordinary sentence long enough."}})
    assert queue[0]["priority"] == "medium"
    assert queue[0]["gemini_label_agree"] == "no"
    assert queue[0]["systems_disagreeing"].startswith("2/3")


def test_cohen_kappa():
    assert agreement_study.cohen_kappa(["a", "b"] * 5, ["a", "b"] * 5) == 1.0
    assert abs(agreement_study.cohen_kappa(["a", "a", "b", "b"], ["a", "b", "a", "b"])) < 1e-9


def test_stratified_sample_covers_thin_categories():
    examples = [{"id": f"m{i}", "category_ids": ["misleading"], "label": "compliant"} for i in range(50)]
    examples += [{"id": "alc", "category_ids": ["alcohol"], "label": "non_compliant"}]
    picked = agreement_study.stratified_sample(examples, 5, seed=1)
    assert "alc" in {e["id"] for e in picked}


def test_recall_half_width():
    assert data_quality_report.recall_half_width(74) == 6.8
    assert data_quality_report.recall_half_width(0) is None


def test_annotation_validation():
    examples = {"e1": {"content": "Cures all disease fast", "label": "non_compliant"}}
    good = [{"example_id": "e1", "annotator": "ab", "platform": "meta", "evidence_spans": ["Cures all"]}]
    assert validate_annotations.validate(good, examples) == []
    bad = [
        {"example_id": "nope", "annotator": "ab"},
        {"example_id": "e1", "annotator": "", "platform": "myspace", "evidence_spans": ["not there"]},
        {"example_id": "e1", "annotator": "ab", "policy_as_of": "last year", "colour": "red"},
    ]
    errors = validate_annotations.validate(bad, examples)
    assert any("unknown example_id" in e for e in errors)
    assert any("annotator is required" in e for e in errors)
    assert any("platform='myspace'" in e for e in errors)
    assert any("span not found" in e for e in errors)
    assert any("not YYYY-MM-DD" in e for e in errors)
    assert any("unknown field 'colour'" in e for e in errors)
