"""Optional integrations: local/remote model APIs (Ollama, OpenAI, etc.)."""

from zataone.integrations.ollama import (
    ollama_chat,
    ollama_generate,
    ollama_health,
    ollama_image_describe,
)
from zataone.integrations.gemini import (
    gemini_health,
    gemini_text_chat,
    gemini_vision_image,
    generate_content as gemini_generate_content,
)
from zataone.integrations.openai_chat import (
    chat_completions,
    openai_text_chat,
    openai_vision_image,
)

__all__ = [
    "ollama_chat",
    "ollama_generate",
    "ollama_health",
    "ollama_image_describe",
    "chat_completions",
    "openai_text_chat",
    "openai_vision_image",
    "gemini_health",
    "gemini_text_chat",
    "gemini_vision_image",
    "gemini_generate_content",
]
