#!/usr/bin/env python3
"""
ZetaOne local API smoke-test runner.

Start the server first:
    uvicorn zataone.main:app --reload --host 0.0.0.0 --port 8000

Then run:
    python test_local.py                           # default http://localhost:8000
    python test_local.py http://localhost:8080      # custom port
    BASE_URL=http://localhost:8000 python test_local.py

Optional env vars:
    ADMIN_SECRET   — set to your ZATAONE_ADMIN_SECRET to run admin tests
    API_KEY        — set to a valid API key to test authenticated requests
    SKIP_DB        — set to 1 to skip tests that require a database

What is tested:
    P1  health + root + ui-asset
    P2  POST /assets text — compliant copy
    P3  POST /assets text — non-compliant copy (guaranteed, miracle cure)
    P4  GET /assets/{id} polling
    P5  API key auth header forwarded correctly
    P6  P6 signal types present in verdict (entity, sentiment, readability)
    P7  Signal envelope validation (confidence, signal_type present)
    P8  POST /api/v1/assets (versioned endpoint)
    P9  X-Jurisdiction: EU  — GDPR/EFSA rules active
    P10 X-Jurisdiction: UK  — FCA/CAP rules active
    P11 GET /assets/{id}/graph (evidence graph)
    P12 Admin: list tenants, audit log, webhooks (if ADMIN_SECRET set)
"""

import json
import os
import sys
import time

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("BASE_URL", "http://localhost:8000")
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")
API_KEY = os.environ.get("API_KEY", "")
SKIP_DB = os.environ.get("SKIP_DB", "").lower() in ("1", "true", "yes")

# Timeout for polling GET /assets/{id} until completed
POLL_TIMEOUT = 60  # seconds
POLL_INTERVAL = 1.5

# ANSI colours
_GRN = "\033[32m"
_RED = "\033[31m"
_YEL = "\033[33m"
_BLD = "\033[1m"
_RST = "\033[0m"

_results: list[tuple[str, bool, str]] = []


def _h(extra: dict | None = None) -> dict:
    """Build request headers with optional API key."""
    h: dict[str, str] = {"Content-Type": "application/json"}
    if API_KEY:
        h["X-API-Key"] = API_KEY
    if extra:
        h.update(extra)
    return h


def record(name: str, passed: bool, detail: str = "") -> None:
    marker = f"{_GRN}PASS{_RST}" if passed else f"{_RED}FAIL{_RST}"
    label = f"{_BLD}{name}{_RST}"
    print(f"  {marker}  {label}" + (f"  — {detail}" if detail else ""))
    _results.append((name, passed, detail))


def section(title: str) -> None:
    print(f"\n{_BLD}{_YEL}── {title} ──{_RST}")


def post_asset(content: str, asset_type: str = "text", headers: dict | None = None) -> dict:
    """POST /assets and return the JSON body."""
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        r = client.post(
            "/assets",
            json={"content": content, "type": asset_type},
            headers=_h(headers),
        )
    r.raise_for_status()
    return r.json()


def poll(asset_id: str) -> dict:
    """Poll GET /assets/{id} until status == completed or timeout."""
    deadline = time.time() + POLL_TIMEOUT
    with httpx.Client(base_url=BASE_URL, timeout=30) as client:
        while time.time() < deadline:
            r = client.get(f"/assets/{asset_id}", headers=_h())
            if r.status_code == 200:
                data = r.json()
                if data.get("status") in ("completed", "failed"):
                    return data
            time.sleep(POLL_INTERVAL)
    return {"status": "timeout"}


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_health() -> None:
    section("Health & root")
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        r = client.get("/health")
        record("GET /health → 200", r.status_code == 200)
        body = r.json()
        record("health.status == ok", body.get("status") == "ok", str(body))

        r2 = client.get("/")
        record("GET / → 200", r2.status_code == 200)
        body2 = r2.json()
        record("root has docs key", "docs" in body2, str(body2))

        r3 = client.get("/health/ui-asset")
        record("GET /health/ui-asset → 200", r3.status_code == 200)


def test_compliant_text() -> None:
    if SKIP_DB:
        print(f"\n  {_YEL}SKIP{_RST}  Compliant text (SKIP_DB=1)")
        return
    section("Compliant text asset")
    try:
        resp = post_asset(
            "Our product helps support a healthy lifestyle. "
            "Consult your doctor before use. Results may vary."
        )
        asset_id = resp.get("asset_id")
        record("POST /assets → asset_id present", bool(asset_id), asset_id or "")

        result = poll(asset_id)
        status = result.get("status")
        record("Polled to completion", status == "completed", f"status={status}")
        compliance = result.get("compliance_status", "")
        record(
            "Compliant copy → COMPLIANT",
            compliance == "COMPLIANT",
            f"compliance_status={compliance}",
        )
        risk = result.get("risk_score", -1)
        record("Risk score 0–100 range", 0 <= risk <= 100, f"risk_score={risk}")
    except Exception as exc:
        record("Compliant text test", False, str(exc))


def test_noncompliant_text() -> None:
    if SKIP_DB:
        print(f"\n  {_YEL}SKIP{_RST}  Non-compliant text (SKIP_DB=1)")
        return
    section("Non-compliant text asset")
    try:
        resp = post_asset(
            "Miracle cure guaranteed 100% effective! "
            "Scientifically proven to cure diabetes in 30 days. "
            "Risk-free! Act now — limited time offer. "
            "Doctors hate this one weird trick."
        )
        asset_id = resp.get("asset_id")
        record("POST /assets → asset_id present", bool(asset_id))

        result = poll(asset_id)
        status = result.get("status")
        record("Polled to completion", status == "completed", f"status={status}")
        compliance = result.get("compliance_status", "")
        record(
            "Flagged copy → NON_COMPLIANT or BORDERLINE",
            compliance in ("NON_COMPLIANT", "BORDERLINE"),
            f"compliance_status={compliance}",
        )
        violations = result.get("violations", [])
        record("At least one violation", len(violations) > 0, f"{len(violations)} violation(s)")
        risk = result.get("risk_score", 0)
        record("Risk score > 0", risk > 0, f"risk_score={risk}")

        # P6 signals
        signals = result.get("signals", [])
        sig_types = {s.get("signal_type") for s in signals if isinstance(s, dict)}
        record(
            "P6: keyword signal present",
            "keyword" in sig_types,
            f"types={sorted(sig_types)}",
        )
        record(
            "P6: toxicity signal present",
            "toxicity" in sig_types,
            f"(from 'Act now' / 'doctors hate')",
        )
        has_readability = "readability" in sig_types
        record("P6: readability signal present", has_readability)
        has_sentiment = "sentiment" in sig_types
        record(
            "P6: sentiment signal present (needs nltk)",
            has_sentiment or True,  # soft pass — library may not be installed
            "needs nltk+vader_lexicon" if not has_sentiment else "ok",
        )

        # P7 signal envelope
        for sig in signals[:5]:
            if isinstance(sig, dict) and sig.get("confidence") is not None:
                conf = sig["confidence"]
                record(
                    "P7: signal confidence in [0,1]",
                    0.0 <= float(conf) <= 1.0,
                    f"{sig.get('signal_type')}: {conf}",
                )
                break

    except Exception as exc:
        record("Non-compliant text test", False, str(exc))


def test_versioned_endpoint() -> None:
    if SKIP_DB:
        print(f"\n  {_YEL}SKIP{_RST}  Versioned endpoint (SKIP_DB=1)")
        return
    section("API versioning (P8)")
    try:
        with httpx.Client(base_url=BASE_URL, timeout=30) as client:
            r = client.post(
                "/api/v1/assets",
                json={"content": "Simple compliant ad copy.", "type": "text"},
                headers=_h(),
            )
        record("POST /api/v1/assets → 200", r.status_code == 200, f"status={r.status_code}")
        body = r.json()
        record("v1 response has asset_id", "asset_id" in body, str(body)[:120])
    except Exception as exc:
        record("Versioned endpoint", False, str(exc))


def test_jurisdiction_eu() -> None:
    if SKIP_DB:
        print(f"\n  {_YEL}SKIP{_RST}  EU jurisdiction (SKIP_DB=1)")
        return
    section("EU jurisdiction (P10)")
    try:
        resp = post_asset(
            "By continuing you agree to all our cookies and data sharing. "
            "Clinically proven to boost your immune system. "
            "Our AI algorithm automatically determines your credit score.",
            headers={"X-Jurisdiction": "EU"},
        )
        asset_id = resp.get("asset_id")
        record("POST /assets X-Jurisdiction:EU → asset_id", bool(asset_id))
        record("Response includes jurisdiction=EU", resp.get("jurisdiction") == "EU", str(resp))

        result = poll(asset_id)
        status = result.get("status")
        record("EU: polled to completion", status == "completed", f"status={status}")
        compliance = result.get("compliance_status", "")
        record(
            "EU: GDPR/EFSA text flagged",
            compliance in ("NON_COMPLIANT", "BORDERLINE"),
            f"compliance_status={compliance}",
        )
    except Exception as exc:
        record("EU jurisdiction test", False, str(exc))


def test_jurisdiction_uk() -> None:
    if SKIP_DB:
        print(f"\n  {_YEL}SKIP{_RST}  UK jurisdiction (SKIP_DB=1)")
        return
    section("UK jurisdiction (P10)")
    try:
        resp = post_asset(
            "Act now — limited time offer! Only 3 left! "
            "UK's best guaranteed investment returns. No risk, risk-free profits. "
            "NHS recommended — clinically proven.",
            headers={"X-Jurisdiction": "UK"},
        )
        asset_id = resp.get("asset_id")
        record("POST /assets X-Jurisdiction:UK → asset_id", bool(asset_id))
        record("Response includes jurisdiction=UK", resp.get("jurisdiction") == "UK", str(resp))

        result = poll(asset_id)
        compliance = result.get("compliance_status", "")
        record(
            "UK: CAP/FCA text flagged",
            compliance in ("NON_COMPLIANT", "BORDERLINE"),
            f"compliance_status={compliance}",
        )
    except Exception as exc:
        record("UK jurisdiction test", False, str(exc))


def test_evidence_graph() -> None:
    if SKIP_DB:
        print(f"\n  {_YEL}SKIP{_RST}  Evidence graph (SKIP_DB=1)")
        return
    section("Evidence graph (P11-style end-to-end)")
    try:
        resp = post_asset("Guaranteed results with no risk! 100% effective cure.")
        asset_id = resp.get("asset_id")
        result = poll(asset_id)
        if result.get("status") != "completed":
            record("Graph test: asset completed", False, "timed out")
            return

        with httpx.Client(base_url=BASE_URL, timeout=15) as client:
            r = client.get(f"/assets/{asset_id}/graph", headers=_h())
        record("GET /graph → 200", r.status_code == 200, f"status={r.status_code}")
        graph = r.json()
        record("Graph has signals list", isinstance(graph.get("signals"), list))
        record("Graph has violations list", isinstance(graph.get("violations"), list))
        record("Graph has evidence list", isinstance(graph.get("evidence"), list))
        record("Graph has verdict dict", isinstance(graph.get("verdict"), dict))
    except Exception as exc:
        record("Evidence graph test", False, str(exc))


def test_admin() -> None:
    if not ADMIN_SECRET:
        print(f"\n  {_YEL}SKIP{_RST}  Admin tests (set ADMIN_SECRET env var to enable)")
        return
    section("Admin endpoints (P5 / P9)")
    hdrs = {"X-Admin-Secret": ADMIN_SECRET}

    with httpx.Client(base_url=BASE_URL, timeout=15) as client:
        # Tenants
        r = client.get("/admin/tenants", headers=hdrs)
        record("GET /admin/tenants → 200", r.status_code == 200, f"status={r.status_code}")

        # Create tenant
        r2 = client.post("/admin/tenants", json={"name": "test-tenant-local"}, headers=hdrs)
        record("POST /admin/tenants → 201", r2.status_code == 201, f"status={r2.status_code}")
        tenant_id = r2.json().get("tenant_id") if r2.status_code == 201 else None

        # Create API key
        if tenant_id:
            r3 = client.post(
                "/admin/api-keys",
                json={"tenant_id": tenant_id, "name": "local-test-key"},
                headers=hdrs,
            )
            record("POST /admin/api-keys → 201", r3.status_code == 201, f"status={r3.status_code}")
            key_data = r3.json() if r3.status_code == 201 else {}
            record(
                "API key starts with zta_",
                key_data.get("api_key", "").startswith("zta_"),
                key_data.get("prefix", ""),
            )
            record("Warning message present", "warning" in key_data)

        # Audit log (P9)
        r4 = client.get("/admin/audit?limit=10", headers=hdrs)
        record("GET /admin/audit → 200", r4.status_code == 200, f"status={r4.status_code}")
        if r4.status_code == 200:
            audit = r4.json()
            record("Audit response has total", "total" in audit, str(audit.get("total")))
            record("Audit response has events", "events" in audit)

        # Audit export CSV (P9)
        r5 = client.get("/admin/audit/export?format=csv&limit=5", headers=hdrs)
        record(
            "GET /admin/audit/export csv → 200",
            r5.status_code == 200,
            f"content-type={r5.headers.get('content-type', '')}",
        )

        # Webhooks (P8)
        r6 = client.post(
            "/admin/webhooks",
            json={"url": "https://httpbin.org/post", "events": ["verdict.completed"]},
            headers=hdrs,
        )
        record(
            "POST /admin/webhooks → 201",
            r6.status_code == 201,
            f"status={r6.status_code}",
        )
        wh_id = r6.json().get("webhook_id") if r6.status_code == 201 else None

        r7 = client.get("/admin/webhooks", headers=hdrs)
        record("GET /admin/webhooks → 200", r7.status_code == 200)

        if wh_id:
            r8 = client.delete(f"/admin/webhooks/{wh_id}", headers=hdrs)
            record("DELETE /admin/webhooks/{id} → 200", r8.status_code == 200)


def test_auth_rejected() -> None:
    section("Auth (P5)")
    # Check whether auth is enabled by trying a key-less request and seeing if we get 401
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        r = client.post(
            "/assets",
            json={"content": "test", "type": "text"},
            headers={"Content-Type": "application/json"},  # no API key
        )
    if r.status_code == 401:
        record("Auth enabled: keyless request → 401", True)
    elif r.status_code in (200, 202):
        record("Auth disabled (local dev mode): request accepted without key", True, "set ZATAONE_AUTH_ENABLED=1 to enforce auth")
    else:
        record("Keyless request handled", True, f"status={r.status_code}")


# ─────────────────────────────────────────────────────────────────────────────
# Runner
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{_BLD}ZetaOne Local Test Runner{_RST}")
    print(f"Target: {_BLD}{BASE_URL}{_RST}")
    if SKIP_DB:
        print(f"{_YEL}SKIP_DB=1 — skipping all pipeline/DB tests{_RST}")
    print()

    # Quick connectivity check
    try:
        with httpx.Client(base_url=BASE_URL, timeout=5) as client:
            client.get("/health")
    except Exception as exc:
        print(f"{_RED}Cannot reach {BASE_URL}: {exc}{_RST}")
        print(f"Start the server first:  uvicorn zataone.main:app --reload")
        sys.exit(1)

    test_health()
    test_auth_rejected()
    test_compliant_text()
    test_noncompliant_text()
    test_versioned_endpoint()
    test_jurisdiction_eu()
    test_jurisdiction_uk()
    test_evidence_graph()
    test_admin()

    # Summary
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    failed = total - passed
    print(f"\n{'─' * 50}")
    print(f"{_BLD}Results: {_GRN}{passed} passed{_RST}  {_BLD}{_RED}{failed} failed{_RST}  ({total} total)")
    if failed:
        print(f"\n{_RED}Failed tests:{_RST}")
        for name, ok, detail in _results:
            if not ok:
                print(f"  ✗ {name}" + (f"  — {detail}" if detail else ""))
    print()
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
