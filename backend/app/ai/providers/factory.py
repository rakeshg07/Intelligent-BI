"""LLM Provider Factory configured for Groq, Gemini, and OpenAI."""

from app.ai.providers.base import BaseLLMProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.groq import GroqProvider
from app.ai.providers.mock import MockProvider
from app.core.config import settings


def get_llm_provider(
    provider_name: str | None = None,
    model_name: str | None = None,
) -> BaseLLMProvider:
    """Instantiate configured LLM provider."""
    provider = (provider_name or settings.LLM_PROVIDER or "groq").lower()
    model = model_name or settings.LLM_MODEL

    if provider == "gemini":
        if settings.GEMINI_API_KEY:
            return GeminiProvider(
                model=model or "gemini-flash-lite-latest", api_key=settings.GEMINI_API_KEY
            )
        return MockProvider(model="mock-analyst")

    if provider == "groq":
        if settings.GROQ_API_KEY:
            return GroqProvider(model=model or "openai/gpt-oss-120b", api_key=settings.GROQ_API_KEY)
        return MockProvider(model="mock-analyst")

    if settings.GROQ_API_KEY:
        return GroqProvider(model=model or "openai/gpt-oss-120b", api_key=settings.GROQ_API_KEY)

    return MockProvider(model="mock-analyst")
