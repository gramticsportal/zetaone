"""Load evaluation examples from seed + precedent-derived files.

Live eval lives in `examples/eval/`. Harvest candidates, quarantine dumps, and
audit CSVs live in `examples/harvest/` and are never loaded here.
"""
from __future__ import annotations

import os
from typing import Iterable

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

EVAL_SUBDIR = "eval"
HARVEST_SUBDIR = "harvest"

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
# minimal pairs built from it. Included by default: we treat the whole labeled set as one
# eval corpus (no active train/dev). Set ZATAONE_EVAL_INCLUDE_HARVESTED=0 to drop them.
#
# The two load together on purpose. The harvested rows are almost entirely non-compliant,
# so loading them alone skews the set ~12:1 toward positives and inflates any metric that
# rewards firing. The pairs are what keep it honest.
HARVESTED_FILES = (
    "eval_harvested.yaml",
    "eval_compliant_pairs.yaml",
)


def eval_dir(root: str | None = None) -> str:
    return os.path.join(root or ROOT, "examples", EVAL_SUBDIR)


def harvest_dir(root: str | None = None) -> str:
    return os.path.join(root or ROOT, "examples", HARVEST_SUBDIR)


def load_yaml(path: str) -> dict:
    # Explicit encoding: the eval rows carry curly quotes and en dashes, which the
    # Windows default (cp1252) cannot decode.
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_eval_examples(
    root: str | None = None,
    splits: Iterable[str] | None = None,
) -> list[dict]:
    """Return merged examples from all eval YAML files (seed first, then precedents)."""
    examples, _ = load_eval_with_sources(root, splits)
    return examples


def _eval_files() -> tuple[str, ...]:
    profile = (os.environ.get("ZATAONE_EVAL_PROFILE") or "full").strip().lower()
    files = EVAL_FILES_CLEAN if profile in ("clean", "denoised") else EVAL_FILES
    raw = (os.environ.get("ZATAONE_EVAL_INCLUDE_HARVESTED") or "1").strip().lower()
    if raw not in ("0", "false", "no", "off"):
        files = files + HARVESTED_FILES
    return files


def _requested_splits(splits: Iterable[str] | None) -> set[str] | None:
    """Splits to keep, or None for all rows.

    Rows are labeled ``test`` for now — there is no active train/dev partition. Optional
    ``ZATAONE_EVAL_SPLITS`` still filters if you set it; default is the full eval set.
    """
    if splits is None:
        raw = os.environ.get("ZATAONE_EVAL_SPLITS") or ""
        splits = [s for s in (p.strip() for p in raw.split(",")) if s]
    wanted = {str(s).strip().lower() for s in splits if str(s).strip()}
    return wanted or None


def load_eval_with_sources(
    root: str | None = None,
    splits: Iterable[str] | None = None,
) -> tuple[list[dict], dict[str, str]]:
    """Return (examples, example_id -> source filename), optionally one split only."""
    eval_root = eval_dir(root)
    wanted = _requested_splits(splits)
    out: list[dict] = []
    sources: dict[str, str] = {}
    for fname in _eval_files():
        path = os.path.join(eval_root, fname)
        if os.path.isfile(path):
            for e in load_yaml(path).get("examples", []) or []:
                # Missing split ⇒ treat as eval/test so seed rows stay in the full set.
                row_split = str(e.get("split") or "test").lower()
                if wanted and row_split not in wanted:
                    continue
                out.append(e)
                sources[e["id"]] = fname
    return out, sources


def eval_file_for_example(example_id: str, root: str | None = None) -> str:
    """Return the source filename for an example id (for error messages)."""
    _, sources = load_eval_with_sources(root)
    return sources.get(example_id, "eval")
