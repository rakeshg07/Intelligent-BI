"""OpenAI LLM Provider using direct HTTP API."""

import json
from typing import Any

import httpx

from app.ai.providers.base import BaseLLMProvider, LLMMessage, LLMResponse, ToolCall
from app.core.errors import AppException


class OpenAIProvider(BaseLLMProvider):
    """OpenAI / OpenAI-compatible provider with native tool calling."""

    def __init__(self, model: str = "gpt-4o", api_key: str = "", base_url: str = ""):
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1/chat/completions",
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.api_key and "localhost" not in self.base_url:
            raise AppException(
                "OpenAI API key is not configured. Set OPENAI_API_KEY in settings or environment."
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        openai_messages: list[dict[str, Any]] = []
        for m in messages:
            msg_dict: dict[str, Any] = {"role": m.role}
            if m.content is not None:
                msg_dict["content"] = m.content
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if m.name:
                msg_dict["name"] = m.name
            if m.tool_calls:
                tc_list = []
                for tc in m.tool_calls:
                    tc_item: dict[str, Any] = {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    if tc.extra_content:
                        tc_item["extra_content"] = tc.extra_content
                    tc_list.append(tc_item)
                msg_dict["tool_calls"] = tc_list
            openai_messages.append(msg_dict)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(self.base_url, headers=headers, json=payload)
            if resp.status_code != 200:
                raise AppException(f"OpenAI API error ({resp.status_code}): {resp.text}")
            data = resp.json()

        choice = data["choices"][0]
        msg = choice.get("message", {})

        tool_calls: list[ToolCall] = []
        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments", "{}"))
            except Exception:
                args = {}
            tool_calls.append(
                ToolCall(
                    id=tc.get("id", ""),
                    name=fn.get("name", ""),
                    arguments=args,
                    extra_content=tc.get("extra_content"),
                )
            )

        return LLMResponse(
            content=msg.get("content"),
            tool_calls=tool_calls,
            finish_reason=choice.get("finish_reason", "stop"),
            provider="openai",
            model=self.model,
        )
