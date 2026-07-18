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


def load_yaml(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_eval_examples(root: str | None = None) -> list[dict]:
    """Return merged examples from all eval YAML files (seed first, then precedents)."""
    examples, _ = load_eval_with_sources(root)
    return examples


def load_eval_with_sources(root: str | None = None) -> tuple[list[dict], dict[str, str]]:
    """Return (examples, example_id -> source filename)."""
    base = root or ROOT
    examples_dir = os.path.join(base, "examples")
    out: list[dict] = []
    sources: dict[str, str] = {}
    for fname in EVAL_FILES:
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
