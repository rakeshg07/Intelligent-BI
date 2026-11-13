"""Anthropic Claude LLM Provider using direct HTTP API."""

from typing import Any

import httpx

from app.ai.providers.base import BaseLLMProvider, LLMMessage, LLMResponse, ToolCall
from app.core.errors import AppException


class ClaudeProvider(BaseLLMProvider):
    """Anthropic Claude Provider with native tool calling."""

    def __init__(
        self, model: str = "claude-3-5-sonnet-20241022", api_key: str = "", base_url: str = ""
    ):
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url or "https://api.anthropic.com/v1/messages",
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.api_key:
            raise AppException(
                "Anthropic API key is not configured. Set ANTHROPIC_API_KEY in settings or environment."
            )

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Extract system prompt if present
        system_content = ""
        claude_messages: list[dict[str, Any]] = []

        for m in messages:
            if m.role == "system":
                system_content = m.content or ""
            elif m.role == "tool":
                claude_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": m.tool_call_id,
                                "content": m.content,
                            }
                        ],
                    }
                )
            elif m.role == "assistant" and m.tool_calls:
                content_blocks: list[dict[str, Any]] = []
                if m.content:
                    content_blocks.append({"type": "text", "text": m.content})
                for tc in m.tool_calls:
                    content_blocks.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                claude_messages.append({"role": "assistant", "content": content_blocks})
            else:
                claude_messages.append({"role": m.role, "content": m.content or ""})

        # Format tools for Claude
        claude_tools = []
        if tools:
            for t in tools:
                fn = t.get("function", t)
                claude_tools.append(
                    {
                        "name": fn["name"],
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
                    }
                )

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": temperature,
            "messages": claude_messages,
        }
        if system_content:
            payload["system"] = system_content
        if claude_tools:
            payload["tools"] = claude_tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self.base_url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise AppException(f"Anthropic API error ({resp.status_code}): {resp.text}")
            data = resp.json()

        # Parse response blocks
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )

        stop_reason = data.get("stop_reason", "stop")
        finish_reason = "tool_calls" if tool_calls else stop_reason

        return LLMResponse(
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
            provider="anthropic",
            model=self.model,
        )
