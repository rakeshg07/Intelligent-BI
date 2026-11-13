"""Google Gemini LLM Provider using Google's native v1beta REST API."""

import json
from typing import Any

import httpx

from app.ai.providers.base import BaseLLMProvider, LLMMessage, LLMResponse, ToolCall
from app.core.errors import AppException

GEMINI_NATIVE_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider with full native function calling and thought signature preservation."""

    def __init__(
        self, model: str = "gemini-flash-lite-latest", api_key: str = "", base_url: str = ""
    ):
        super().__init__(
            model=model or "gemini-flash-lite-latest",
            api_key=api_key,
            base_url=base_url,
        )

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        if not self.api_key:
            raise AppException(
                "Gemini API key is not configured. Set GEMINI_API_KEY in backend/.env."
            )

        # Convert tools to Gemini native function_declarations
        gemini_tools = None
        if tools:
            func_decls = []
            for t in tools:
                fn = t.get("function", {})
                params = fn.get("parameters", {})
                func_decls.append(
                    {
                        "name": fn.get("name"),
                        "description": fn.get("description", ""),
                        "parameters": self._convert_json_schema(params),
                    }
                )
            gemini_tools = [{"function_declarations": func_decls}]

        # Convert messages to Gemini native contents
        contents: list[dict[str, Any]] = []
        system_instruction: dict[str, Any] | None = None

        for m in messages:
            if m.role == "system":
                system_instruction = {"parts": [{"text": m.content or ""}]}
            elif m.role == "user":
                contents.append(
                    {
                        "role": "user",
                        "parts": [{"text": m.content or ""}],
                    }
                )
            elif m.role == "assistant":
                parts: list[dict[str, Any]] = []
                if m.content:
                    parts.append({"text": m.content})
                if m.tool_calls:
                    for tc in m.tool_calls:
                        part: dict[str, Any] = {
                            "functionCall": {
                                "name": tc.name,
                                "args": tc.arguments,
                            }
                        }
                        if tc.id:
                            part["functionCall"]["id"] = tc.id
                        if tc.extra_content and "thoughtSignature" in tc.extra_content:
                            part["thoughtSignature"] = tc.extra_content["thoughtSignature"]
                        elif tc.extra_content and "google" in tc.extra_content:
                            part["thoughtSignature"] = tc.extra_content["google"].get(
                                "thought_signature"
                            )
                        parts.append(part)
                contents.append({"role": "model", "parts": parts})
            elif m.role == "tool":
                # Function response in Gemini format
                tool_result: Any = {}
                if m.content:
                    try:
                        tool_result = json.loads(m.content)
                    except Exception:
                        tool_result = {"result": m.content}
                response_part: dict[str, Any] = {
                    "functionResponse": {
                        "name": m.name or "tool",
                        "response": {"name": m.name or "tool", "content": tool_result},
                    }
                }
                if m.tool_call_id:
                    response_part["functionResponse"]["id"] = m.tool_call_id
                contents.append(
                    {
                        "role": "user",
                        "parts": [response_part],
                    }
                )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": temperature},
        }
        if system_instruction:
            payload["systemInstruction"] = system_instruction
        if gemini_tools:
            payload["tools"] = gemini_tools

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise AppException(f"Gemini API error ({resp.status_code}): {resp.text}")
            data = resp.json()

        candidates = data.get("candidates", [])
        if not candidates:
            return LLMResponse(
                content="",
                tool_calls=[],
                finish_reason="stop",
                provider="gemini",
                model=self.model,
            )

        cand = candidates[0]
        content_obj = cand.get("content", {})
        cand_parts = content_obj.get("parts", [])

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for p in cand_parts:
            if "text" in p:
                text_parts.append(p["text"])
            if "functionCall" in p:
                fc = p["functionCall"]
                tc_id = fc.get("id") or f"call_{fc.get('name', 'tool')}"
                extra = {}
                if "thoughtSignature" in p:
                    extra["thoughtSignature"] = p["thoughtSignature"]
                tool_calls.append(
                    ToolCall(
                        id=tc_id,
                        name=fc.get("name", ""),
                        arguments=fc.get("args", {}),
                        extra_content=extra or None,
                    )
                )

        return LLMResponse(
            content="".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            finish_reason="tool_calls" if tool_calls else "stop",
            provider="gemini",
            model=self.model,
        )

    def _convert_json_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Convert standard JSON Schema to Gemini uppercase types."""
        if not isinstance(schema, dict):
            return {}
        result: dict[str, Any] = {}
        for k, v in schema.items():
            if k == "type" and isinstance(v, str):
                result["type"] = v.upper()
            elif k == "properties" and isinstance(v, dict):
                result["properties"] = {pk: self._convert_json_schema(pv) for pk, pv in v.items()}
            elif k == "items" and isinstance(v, dict):
                result["items"] = self._convert_json_schema(v)
            else:
                result[k] = v
        return result
