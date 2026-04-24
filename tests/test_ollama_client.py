"""Ollama client: integration test only if Ollama is running locally."""

import os

import pytest

httpx = pytest.importorskip("httpx", reason="httpx required")


@pytest.mark.integration
def test_ollama_health_and_ping():
    from zataone.integrations.ollama import ollama_generate, ollama_health

    if not ollama_health():
        pytest.skip("Ollama not reachable at OLLAMA_BASE_URL (default http://127.0.0.1:11434)")

    model = os.environ.get("OLLAMA_LLM_MODEL", "llama3.2")
    out = ollama_generate("Reply with the single word: ok", model=model)
    assert isinstance(out, str) and len(out) > 0
