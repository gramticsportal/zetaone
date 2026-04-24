"""Gemini client: optional live test if GEMINI_API_KEY or GOOGLE_API_KEY is set."""

import os

import pytest

httpx = pytest.importorskip("httpx", reason="httpx required")


@pytest.mark.integration
def test_gemini_text_smoke():
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        pytest.skip("Set GEMINI_API_KEY or GOOGLE_API_KEY for live Gemini test")

    from zataone.integrations.gemini import gemini_text_chat

    out = gemini_text_chat('Reply with exactly the word "pong".', max_output_tokens=32)
    assert isinstance(out, str) and len(out) > 0
