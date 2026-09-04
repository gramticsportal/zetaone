#!/usr/bin/env python3
"""Canonical matcher eval — use this script, not ad-hoc runners.

Scores the hybrid lexical matcher (NLP off) on the full live eval set, then the
compliant/non-compliant pair task.

Live eval = seed + precedents + harvested + pairs (all rows, no train/dev).
Quarantine files under ontology/examples/harvest/ are not loaded.

Usage (repo root):
  PYTHONPATH=src python3.11 scripts/eval_matcher.py
  PYTHONPATH=src python3.11 scripts/eval_matcher.py --skip-pairs
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _lock_env() -> None:
    os.environ["ZATAONE_HYBRID_ENGINE"] = "1"
    os.environ["ZATAONE_HYBRID_NLP"] = "0"
    os.environ["ZATAONE_HYBRID_NLP_BACKEND"] = "bow"
    os.environ.pop("ZATAONE_EVAL_SPLITS", None)
    os.environ.pop("ZATAONE_SEMANTIC_CLASSIFIER", None)
    os.environ.pop("ZATAONE_HYBRID_MIN_CONFIDENCE", None)
    # Full corpus: harvested + pairs on (loader default is already 1).
    os.environ.setdefault("ZATAONE_EVAL_INCLUDE_HARVESTED", "1")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-pairs", action="store_true")
    parser.add_argument("--skip-full", action="store_true")
    args = parser.parse_args()

    _lock_env()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + str(ROOT / "ontology") + os.pathsep + env.get(
        "PYTHONPATH", ""
    )

    if not args.skip_full:
        print("=" * 60, flush=True)
        print("MATCHER EVAL — full live corpus (NLP off)", flush=True)
        print("=" * 60, flush=True)
        rc = subprocess.call(
            [sys.executable, str(ROOT / "scripts" / "eval_hybrid_local.py")],
            cwd=str(ROOT),
            env=env,
        )
        if rc != 0:
            return rc

    if not args.skip_pairs:
        print(flush=True)
        print("=" * 60, flush=True)
        print("MATCHER EVAL — compliant/violation pairs (split=all)", flush=True)
        print("=" * 60, flush=True)
        rc = subprocess.call(
            [sys.executable, str(ROOT / "ontology" / "tools" / "eval_matcher_pairs.py"), "--split", "all"],
            cwd=str(ROOT),
            env=env,
        )
        if rc != 0:
            return rc

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
