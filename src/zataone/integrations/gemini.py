"""
Google Gemini API (Google AI / AI Studio) via REST + httpx — no extra Python package.

Create a key: https://aistudio.google.com/apikey

Env:
  GEMINI_API_KEY or GOOGLE_API_KEY  — required
  GEMINI_MODEL — default gemini-2.0-flash-001 (override if 404: list models, see below)
  GEMINI_VLM_MODEL — optional; vision calls default to GEMINI_MODEL if unset
  GEMINI_VLM_MAX_TOKENS — default 1200 (advisory VLM inspection length)
  GEMINI_TIMEOUT_S — default 120

Docs: https://ai.google.dev/api/generate-content
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx

_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _api_key() -> str:
    k = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not k:
        raise RuntimeError("Set GEMINI_API_KEY (or GOOGLE_API_KEY) for Gemini API calls")
    return k


def _timeout() -> float:
    return float(os.environ.get("GEMINI_TIMEOUT_S") or "120")


def _default_model() -> str:
    # Unversioned ids (e.g. gemini-2.0-flash) can 404 for some keys; use a stable name from:
    #   GET v1beta/models?key=...
    return (os.environ.get("GEMINI_MODEL") or "gemini-2.0-flash-001").strip()


def _parse_text_response(data: dict[str, Any]) -> str:
    cands = data.get("candidates") or []
    if not cands:
        return ""
    content = cands[0].get("content") or {}
    parts = content.get("parts") or []
    out: list[str] = []
    for p in parts:
        t = p.get("text")
        if t:
            out.append(t if isinstance(t, str) else str(t))
    return "".join(out).strip()


def generate_content(
    parts: list[dict[str, Any]],
    *,
    model: str | None = None,
    system_instruction: str | None = None,
    generation_config: dict[str, Any] | None = None,
) -> str:
    """
    POST .../models/{model}:generateContent. `parts` are Gemini `Part` objects (text and/or inlineData).
    See https://ai.google.dev/api/caching#Part
    """
    m = model or _default_model()
    url = f"{_API_BASE}/models/{m}:generateContent"
    body: dict[str, Any] = {
        "contents": [{"role": "user", "parts": parts}],
    }
    if system_instruction:
        body["systemInstruction"] = {
            "parts": [{"text": system_instruction}],
        }
    if generation_config is not None:
        body["generationConfig"] = generation_config

    with httpx.Client(timeout=_timeout()) as c:
        r = c.post(
            url,
            headers={
                "x-goog-api-key": _api_key(),
                "Content-Type": "application/json",
            },
            content=json.dumps(body),
        )
        r.raise_for_status()
        data = r.json()
    return _parse_text_response(data)


def gemini_text_chat(
    user_prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    max_output_tokens: int = 1024,
    temperature: float = 0.2,
    response_mime_type: str | None = None,
) -> str:
    """Text-only. Set response_mime_type to \"application/json\" for JSON mode (when supported)."""
    gen: dict[str, Any] = {
        "maxOutputTokens": max_output_tokens,
        "temperature": temperature,
    }
    if response_mime_type:
        gen["responseMimeType"] = response_mime_type
    return generate_content(
        [{"text": user_prompt}],
        model=model,
        system_instruction=system_prompt,
        generation_config=gen,
    )


def gemini_vision_image(
    image_bytes: bytes,
    user_prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    max_output_tokens: int = 800,
    temperature: float = 0.2,
    mime_type: str = "image/png",
) -> str:
    """One image (inline) + text. Uses camelCase Part.inlineData for JSON API."""
    b64 = base64.b64encode(image_bytes).decode("ascii")
    parts: list[dict[str, Any]] = [
        {"text": user_prompt},
        {
            "inlineData": {
                "mimeType": mime_type,
                "data": b64,
            }
        },
    ]
    return generate_content(
        parts,
        model=model,
        system_instruction=system_prompt,
        generation_config={
            "maxOutputTokens": max_output_tokens,
            "temperature": temperature,
        },
    )


def gemini_health() -> bool:
    """True if the API key is set (does not call the network)."""
    try:
        _api_key()
        return True
    except RuntimeError:
        return False
