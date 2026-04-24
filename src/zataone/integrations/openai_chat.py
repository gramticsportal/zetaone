"""
OpenAI Chat Completions API (text + vision) via httpx. For high-quality models with an API key.

Env:
  OPENAI_API_KEY  — required (falls back to VLM_API_KEY if set, same as modality VLM)
  OPENAI_BASE_URL — default https://api.openai.com/v1
  OPENAI_LLM_MODEL — default gpt-4o-mini  (text-only / review)
  OPENAI_VLM_MODEL — default gpt-4o    (image + text)

Use the same key with:
  - OpenAI direct
  - OpenAI-compatible proxies: set OPENAI_BASE_URL to e.g. https://api.openai.com/v1
    or https://api.x.ai/v1, OpenRouter, etc. (path must end so .../v1 + /chat/completions works)

JSON mode: pass response_format for structured ReviewContext outputs (gpt-4o and compatible models).
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any

import httpx


def _api_key(explicit: str | None = None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    k = (os.environ.get("OPENAI_API_KEY") or os.environ.get("VLM_API_KEY") or "").strip()
    if not k:
        raise RuntimeError("Set OPENAI_API_KEY (or VLM_API_KEY) for OpenAI API calls")
    return k


def _base() -> str:
    return (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")


def _timeout() -> float:
    return float(os.environ.get("OPENAI_TIMEOUT_S") or "120")


def chat_completions(
    messages: list[dict[str, Any]],
    *,
    model: str,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    response_format: dict[str, str] | None = None,
    api_key: str | None = None,
) -> str:
    """
    POST /v1/chat/completions. Returns assistant message text (string content only).
    """
    url = f"{_base()}/chat/completions"
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if response_format is not None:
        body["response_format"] = response_format
    with httpx.Client(timeout=_timeout()) as c:
        r = c.post(
            url,
            headers={
                "Authorization": f"Bearer {_api_key(api_key)}",
                "Content-Type": "application/json",
            },
            content=json.dumps(body),
        )
        r.raise_for_status()
        out = r.json()
    text = (out.get("choices") or [{}])[0].get("message", {}).get("content", "")
    if not isinstance(text, str):
        text = str(text)
    return text.strip()


def openai_text_chat(
    user_prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    max_tokens: int = 1024,
    temperature: float = 0.2,
    response_format: dict[str, str] | None = None,
    api_key: str | None = None,
) -> str:
    """Text-only. Model defaults to OPENAI_LLM_MODEL or gpt-4o-mini."""
    m = model or os.environ.get("OPENAI_LLM_MODEL") or "gpt-4o-mini"
    msgs: list[dict[str, Any]] = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": user_prompt})
    return chat_completions(
        msgs,
        model=m,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format=response_format,
        api_key=api_key,
    )


def openai_vision_image(
    image_bytes: bytes,
    user_prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    max_tokens: int = 800,
    temperature: float = 0.2,
    image_media_type: str = "image/png",
    api_key: str | None = None,
) -> str:
    """
    One image + text. Model defaults to OPENAI_VLM_MODEL or gpt-4o.
    """
    m = model or os.environ.get("OPENAI_VLM_MODEL") or "gpt-4o"
    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{image_media_type};base64,{b64}"
    user_content: list[dict[str, Any]] = [
        {"type": "text", "text": user_prompt},
        {"type": "image_url", "image_url": {"url": data_url}},
    ]
    msgs: list[dict[str, Any]] = []
    if system_prompt:
        msgs.append({"role": "system", "content": system_prompt})
    msgs.append({"role": "user", "content": user_content})
    return chat_completions(
        msgs,
        model=m,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=api_key,
    )
