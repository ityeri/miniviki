import json
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..errors import MinivikiError
from .types import Completion, Message, ToolCall, ToolSchema


def to_openai_messages(messages: list[Message]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        raw: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            raw["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)}
                }
                for call in message.tool_calls
            ]
        if message.tool_call_id is not None:
            raw["tool_call_id"] = message.tool_call_id
        converted.append(raw)
    return converted


def to_openai_tools(tools: list[ToolSchema]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters or {"type": "object", "properties": {}}
            }
        }
        for tool in tools
    ]


def from_openai_response(raw_data: dict[str, Any]) -> Completion:
    choices = raw_data.get("choices") or []
    if not choices:
        raise MinivikiError("provider returned no choices")
    message = choices[0].get("message") or {}
    calls: list[ToolCall] = []
    for item in message.get("tool_calls") or []:
        function = item.get("function") or {}
        try:
            arguments = json.loads(function.get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        calls.append(
            ToolCall(
                id=str(item.get("id", "")),
                name=str(function.get("name", "")),
                arguments=arguments
            )
        )
    usage = raw_data.get("usage") or {}
    prompt_details = usage.get("prompt_tokens_details") or {}
    return Completion(
        message=Message(
            role=str(message.get("role", "assistant")),
            content=str(message.get("content") or ""),
            tool_calls=tuple(calls)
        ),
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        completion_tokens=int(usage.get("completion_tokens", 0)),
        cached_tokens=int(prompt_details.get("cached_tokens", 0))
    )


@dataclass(slots=True)
class OpenAICompatClient:
    """Talks to any OpenAI-shaped endpoint. The translation lives here, not in the loop."""

    base_url: str
    api_key: str
    model: str
    timeout: float = 120.0
    http: httpx.AsyncClient = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.http is None:
            self.http = httpx.AsyncClient(timeout=self.timeout)

    def _payload(self, messages: list[Message], tools: list[ToolSchema]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_messages(messages)
        }
        if tools:
            payload["tools"] = to_openai_tools(tools)
        return payload

    async def complete(self, messages, tools=()) -> Completion:
        response = await self.http.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=self._payload(list(messages), list(tools))
        )
        response.raise_for_status()
        return from_openai_response(response.json())

    async def stream(self, messages, tools=()):
        payload = self._payload(list(messages), list(tools)) | {"stream": True}
        async with self.http.stream(
            "POST",
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                body = line[len("data: "):]
                if body.strip() == "[DONE]":
                    break
                chunk = json.loads(body)
                delta = (chunk.get("choices") or [{}])[0].get("delta") or {}
                text = delta.get("content")
                if text:
                    yield str(text)

    async def aclose(self) -> None:
        await self.http.aclose()
