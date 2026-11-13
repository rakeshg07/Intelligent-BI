"""Hugging Face Inference API Provider (OpenAI-compatible /v1/chat/completions)."""

from typing import Any

from app.ai.providers.base import LLMMessage, LLMResponse
from app.ai.providers.openai import OpenAIProvider
from app.core.errors import AppException

HUGGINGFACE_ROUTER_URL = "https://router.huggingface.co/v1/chat/completions"


class HuggingFaceProvider(OpenAIProvider):
    """Hugging Face provider using the OpenAI-compatible chat completions router."""

    def __init__(
        self,
        model: str = "Qwen/Qwen2.5-Coder-32B-Instruct",
        api_key: str = "",
        base_url: str = "",
    ):
        super().__init__(
            model=model or "Qwen/Qwen2.5-Coder-32B-Instruct",
            api_key=api_key,
            base_url=base_url or HUGGINGFACE_ROUTER_URL,
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.api_key:
            raise AppException(
                "Hugging Face API key is not configured. Set HUGGINGFACE_API_KEY in backend/.env."
            )

        resp = await super().generate(messages=messages, tools=tools, temperature=temperature)
        resp.provider = "huggingface"
        return resp
