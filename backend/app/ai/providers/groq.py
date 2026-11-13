"""Groq LLM Provider using Groq's high-speed OpenAI-compatible API."""

from typing import Any

from app.ai.providers.base import LLMMessage, LLMResponse
from app.ai.providers.openai import OpenAIProvider
from app.core.errors import AppException

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(OpenAIProvider):
    """Groq provider with ultra-fast inference and native tool calling."""

    def __init__(
        self,
        model: str = "openai/gpt-oss-120b",
        api_key: str = "",
        base_url: str = "",
    ):
        super().__init__(
            model=model or "openai/gpt-oss-120b",
            api_key=api_key,
            base_url=base_url or GROQ_API_URL,
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.api_key:
            raise AppException("Groq API key is not configured. Set GROQ_API_KEY in backend/.env.")

        resp = await super().generate(messages=messages, tools=tools, temperature=temperature)
        resp.provider = "groq"
        return resp
