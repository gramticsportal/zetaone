#!/usr/bin/env python3
"""Hit live Cloud Run and print pipeline_timing for a few text/image samples."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

IMGS = Path("/tmp/zataone_profile_imgs")


def base_url() -> str:
    out = subprocess.check_output(
        [
            "gcloud",
            "run",
            "services",
            "describe",
            "zataone-api",
            "--region=us-central1",
            "--project=zetaone-493600",
            "--format=value(status.url)",
        ],
        text=True,
    ).strip()
    return out


def summarize(label: str, data: dict, wall_s: float) -> None:
    m = data.get("metadata") or {}
    pt = m.get("pipeline_timing") or {}
    print(f"=== {label} ===")
    if data.get("detail"):
        print("ERROR:", str(data["detail"])[:400])
        print(f"wall_http_s: {wall_s:.2f}\n")
        return
    print(
        "status:",
        data.get("status") or data.get("display_compliance_status"),
        "verdict:",
        data.get("verdict") or data.get("display_verdict"),
        "risk:",
        data.get("risk_score"),
    )
    print(
        "hybrid:",
        m.get("hybrid_engine"),
        "nlp:",
        m.get("hybrid_nlp_backend"),
        "packs:",
        m.get("hybrid_packs_evaluated"),
        "hy_sig:",
        m.get("hybrid_signal_count"),
    )
    print("extractors:", m.get("extractor_counts"))
    print("timing:", json.dumps(pt))
    print(f"wall_http_s: {wall_s:.2f}\n")


def main() -> int:
    base = base_url()
    print("BASE", base)
    with httpx.Client(base_url=base, timeout=600.0) as client:
        r = client.get("/health")
        print("health", r.status_code, r.text)

        # Warmup
        t0 = time.perf_counter()
        r = client.post(
            "/assets",
            headers={"X-Pipeline-Mode": "full", "X-Domain": "ad_compliance"},
            json={"content": "warmup guaranteed cure 100%", "type": "text"},
        )
        summarize("warmup_text", r.json(), time.perf_counter() - t0)

        for label, content in [
            ("text_health", "Guaranteed miracle overnight cure 100% clinically proven!"),
            (
                "text_academic",
                "Approximation estimation error underfitting overfitting hypothesis class",
            ),
        ]:
            t0 = time.perf_counter()
            r = client.post(
                "/assets",
                headers={"X-Pipeline-Mode": "full", "X-Domain": "ad_compliance"},
                json={"content": content, "type": "text"},
            )
            summarize(label, r.json(), time.perf_counter() - t0)

        for name in ("ad_health.png", "academic.png", "gambling.png"):
            path = IMGS / name
            if not path.is_file():
                print(f"missing {path}")
                continue
            t0 = time.perf_counter()
            with path.open("rb") as f:
                r = client.post(
                    "/assets/image",
                    headers={"X-Pipeline-Mode": "full", "X-Domain": "ad_compliance"},
                    files={"file": (name, f, "image/png")},
                )
            summarize(f"img_{name}", r.json(), time.perf_counter() - t0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
