"""
Ollama HTTP client (text LLM + vision).

**No ollama.com account or API key** is required for the normal setup: install the Ollama app
(or Linux binary), `ollama serve` listens on 11434 with no auth. Pull models with `ollama pull …`.

**Cloud later:** Ollama does not run “inside” stock Cloud Run the way your API does; typical pattern is
Ollama on a **GCE VM / GKE** (or a dedicated host), private network, set **OLLAMA_BASE_URL** to that
internal URL from Cloud Run (Serverless VPC Access / Connector). If you put **nginx in front** with
a shared secret, set **OLLAMA_API_KEY** and we send `Authorization: Bearer …`.

Env (optional):
  OLLAMA_BASE_URL   — default http://127.0.0.1:11434
  OLLAMA_API_KEY   — if your proxy requires Bearer token; omit for open local Ollama
  OLLAMA_LLM_MODEL  — e.g. llama3.2, mistral, qwen2.5
  OLLAMA_VLM_MODEL  — e.g. llava, llava-llama3, qwen2.5-vl:7b (pull with: ollama pull <name>)
  OLLAMA_TIMEOUT_S  — default 120

Run: https://ollama.com — `ollama serve` then `ollama pull llama3.2` and optional `ollama pull llava`.

Other "free for dev" options (same idea, different URL):
  - LM Studio: local server, often OpenAI-compatible (use base URL + /v1/chat/completions).
  - vLLM / Text Generation Inference: self-hosted OpenAI-like APIs.
  - Groq / Together / Google AI Studio: free tiers with API keys, not Ollama-specific.

This module is intentionally small: wire your ReviewPack + prompts later; call ollama_generate / ollama_image_describe from there.
"""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx

DEFAULT_BASE = "http://127.0.0.1:11434"


def _base_url() -> str:
    return (os.environ.get("OLLAMA_BASE_URL") or DEFAULT_BASE).rstrip("/")


def _timeout() -> float:
    return float(os.environ.get("OLLAMA_TIMEOUT_S") or "120")


def _auth_headers() -> dict[str, str]:
    h: dict[str, str] = {}
    key = (os.environ.get("OLLAMA_API_KEY") or "").strip()
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def _post_json(path: str, body: dict[str, Any]) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    with httpx.Client(timeout=_timeout()) as client:
        r = client.post(url, json=body, headers=_auth_headers() or None)
        r.raise_for_status()
        return r.json()


def ollama_chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    stream: bool = False,
) -> str:
    """
    Low-level: POST /api/chat. `messages` are Ollama-style user/assistant/system messages.
    For vision, include base64 in message \"images\" list (see ollama_image_describe).
    """
    m = model or os.environ.get("OLLAMA_LLM_MODEL") or "llama3.2"
    out = _post_json(
        "/api/chat",
        {
            "model": m,
            "messages": messages,
            "stream": stream,
        },
    )
    if stream:
        raise ValueError("stream=True not supported; set stream=False")
    msg = (out.get("message") or {}).get("content", "")
    return msg if isinstance(msg, str) else str(msg)


def ollama_generate(
    prompt: str,
    *,
    system: str | None = None,
    model: str | None = None,
) -> str:
    """Single-turn text generation."""
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return ollama_chat(messages, model=model)


def ollama_image_describe(
    image_bytes: bytes,
    prompt: str = "Describe this image in 2–4 short sentences. Be factual; do not invent text you cannot read.",
    *,
    model: str | None = None,
) -> str:
    """
    VLM: one image (bytes) as base64 in the user message. Requires a vision model in Ollama.
    """
    m = model or os.environ.get("OLLAMA_VLM_MODEL") or "llava"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    out = _post_json(
        "/api/chat",
        {
            "model": m,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [b64],
                }
            ],
            "stream": False,
        },
    )
    msg = (out.get("message") or {}).get("content", "")
    return msg if isinstance(msg, str) else str(msg)


def ollama_health() -> bool:
    """True if Ollama responds (GET /api/tags or similar not always present; we try a tiny request)."""
    try:
        with httpx.Client(timeout=5.0) as c:
            r = c.get(f"{_base_url()}/api/tags", headers=_auth_headers() or None)
            return r.status_code == 200
    except OSError:
        return False
    except httpx.HTTPError:
        return False
