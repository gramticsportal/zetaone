"""
Domain-agnostic VLM API call (OpenAI-compatible chat + vision). Config via args / env.

Uses zataone.integrations.openai_chat (httpx) for a single high-quality code path.
"""

from __future__ import annotations

import os
from typing import Any

from zataone.integrations.openai_chat import openai_vision_image


def analyze_image_context(
    image_bytes: bytes,
    ocr_texts: list[str],
    vision_objects: list[dict[str, Any]],
    policy_id: str,
    *,
    model: str = "gpt-4o",
    max_tokens: int = 120,
    temperature: float = 0.2,
    api_key_env: str = "VLM_API_KEY",
) -> str:
    """
    Short natural-language explanation (<= ~3 sentences). Reads API key from api_key_env.
    """
    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(f"{api_key_env} is not set")

    ocr_texts_clean = [t.strip() for t in (ocr_texts or []) if t and t.strip()][:25]
    objs = []
    for obj in vision_objects or []:
        label = str(obj.get("label", "")).strip()
        if not label:
            continue
        objs.append({"label": label, "confidence": obj.get("confidence")})
    objs = objs[:25]
    policy_name = policy_id.replace("_", " ").strip()

    prompt = (
        "You are helping explain compliance evidence for an ad image.\n"
        "Be factual and neutral. Do NOT give a verdict, policy decision, or score.\n"
        "Respond with at most 3 sentences.\n\n"
        f"Policy: {policy_name}\n"
        f"OCR text snippets: {ocr_texts_clean}\n"
        f"Vision objects: {objs}\n\n"
        "Task: Briefly explain whether the image content and text supports the policy concern, "
        "and note any ambiguity (e.g., medical vs non-medical usage) if relevant."
    )

    text = openai_vision_image(
        image_bytes,
        prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=api_key,
    )
    return text[:600]
