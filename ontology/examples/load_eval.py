"""Load evaluation examples from seed + precedent-derived files."""
from __future__ import annotations

import glob
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EVAL_FILES = (
    "eval_seed.yaml",
    "eval_precedents.yaml",
)

# Denoised seed (no borderline / stubs) + precedents. Set ZATAONE_EVAL_PROFILE=clean
EVAL_FILES_CLEAN = (
    "eval_seed_clean.yaml",
    "eval_precedents.yaml",
)

# Verbatim ad copy harvested from enforcement documents, plus the synthetic compliant
# minimal pairs built from it. Off by default: most harvested rows are still model-triaged
# rather than human-confirmed, so folding them in silently would move every benchmark
# number. Set ZATAONE_EVAL_INCLUDE_HARVESTED=1 to include.
#
# The two load together on purpose. The harvested rows are almost entirely non-compliant,
# so loading them alone skews the set ~12:1 toward positives and inflates any metric that
# rewards firing. The pairs are what keep it honest.
HARVESTED_FILES = (
    "eval_harvested.yaml",
    "eval_compliant_pairs.yaml",
)


def load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_eval_examples(root: str | None = None) -> list[dict]:
    """Return merged examples from all eval YAML files (seed first, then precedents)."""
    examples, _ = load_eval_with_sources(root)
    return examples


def _eval_files() -> tuple[str, ...]:
    profile = (os.environ.get("ZATAONE_EVAL_PROFILE") or "full").strip().lower()
    files = EVAL_FILES_CLEAN if profile in ("clean", "denoised") else EVAL_FILES
    if (os.environ.get("ZATAONE_EVAL_INCLUDE_HARVESTED") or "").strip().lower() in ("1", "true", "yes"):
        files = files + HARVESTED_FILES
    return files


def load_eval_with_sources(root: str | None = None) -> tuple[list[dict], dict[str, str]]:
    """Return (examples, example_id -> source filename)."""
    base = root or ROOT
    examples_dir = os.path.join(base, "examples")
    out: list[dict] = []
    sources: dict[str, str] = {}
    for fname in _eval_files():
        path = os.path.join(examples_dir, fname)
        if os.path.isfile(path):
            for e in load_yaml(path).get("examples", []) or []:
                out.append(e)
                sources[e["id"]] = fname
    return out, sources


def eval_file_for_example(example_id: str, root: str | None = None) -> str:
    """Return the source filename for an example id (for error messages)."""
    _, sources = load_eval_with_sources(root)
    return sources.get(example_id, "eval")
