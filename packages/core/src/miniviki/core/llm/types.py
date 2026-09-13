from dataclasses import dataclass, field
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return ToolCall(
            id=str(raw_data["id"]),
            name=str(raw_data["name"]),
            arguments=dict(raw_data.get("arguments") or {})
        )


@dataclass(frozen=True, slots=True)
class Message:
    role: str
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    name: str | None = None

    def to_json(self) -> dict[str, Any]:
        raw: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            raw["tool_calls"] = [
                {"id": call.id, "name": call.name, "arguments": call.arguments}
                for call in self.tool_calls
            ]
        if self.tool_call_id is not None:
            raw["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            raw["name"] = self.name
        return raw


@dataclass(frozen=True, slots=True)
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return ToolSchema(
            name=str(raw_data["name"]),
            description=str(raw_data.get("description", "")),
            parameters=dict(raw_data.get("parameters") or {})
        )


@dataclass(frozen=True, slots=True)
class Completion:
    message: Message
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
