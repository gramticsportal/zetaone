"""Ollama client: integration test only if Ollama is running locally."""

import os

import pytest

httpx = pytest.importorskip("httpx", reason="httpx required")


def test_ollama_structured_chat_and_telemetry(monkeypatch):
    from zataone.integrations import ollama as ollama_mod

    seen = {}

    def _fake(path, body):
        seen.update(path=path, body=body)
        return {
            "model": "qwen3:8b",
            "message": {"content": '{"summary":"ok"}'},
            "total_duration": 1_500_000_000,
            "load_duration": 100_000_000,
            "prompt_eval_duration": 600_000_000,
            "eval_duration": 800_000_000,
            "prompt_eval_count": 100,
            "eval_count": 20,
            "done_reason": "stop",
        }

    monkeypatch.setattr(ollama_mod, "_post_json", _fake)
    result = ollama_mod.ollama_chat_detailed(
        [{"role": "user", "content": "review"}],
        model="qwen3:8b",
        response_format={"type": "object"},
        options={"temperature": 0, "num_ctx": 32768},
        keep_alive="15m",
        think=False,
    )

    assert result.text == '{"summary":"ok"}'
    assert result.total_duration_ms == 1500
    assert result.prompt_tokens == 100
    assert result.output_tokens == 20
    assert result.done_reason == "stop"
    assert seen["path"] == "/api/chat"
    assert seen["body"]["format"] == {"type": "object"}
    assert seen["body"]["options"]["temperature"] == 0
    assert seen["body"]["keep_alive"] == "15m"
    assert seen["body"]["think"] is False


@pytest.mark.integration
def test_ollama_health_and_ping():
    from zataone.integrations.ollama import ollama_generate, ollama_health

    if not ollama_health():
        pytest.skip("Ollama not reachable at OLLAMA_BASE_URL (default http://127.0.0.1:11434)")

    model = os.environ.get("OLLAMA_LLM_MODEL", "qwen3:8b")
    out = ollama_generate("Reply with the single word: ok", model=model)
    assert isinstance(out, str) and len(out) > 0
