from dataclasses import dataclass, field

from .types import Completion, Message, ToolCall


def reply(text: str, prompt_tokens: int = 0, completion_tokens: int = 0) -> Completion:
    return Completion(
        message=Message(role="assistant", content=text),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens
    )


def call(
    name: str,
    arguments: dict | None = None,
    call_id: str = "c1",
    content: str = ""
) -> Completion:
    tool_call = ToolCall(id=call_id, name=name, arguments=dict(arguments or {}))
    return Completion(message=Message(role="assistant", content=content, tool_calls=(tool_call,)))


@dataclass(slots=True)
class ScriptedClient:
    """Replays a fixed script. Deterministic, offline, and enough to exercise the whole loop."""

    script: list[Completion] = field(default_factory=list)
    seen: list[list[Message]] = field(default_factory=list)
    tools_seen: list[tuple[str, ...]] = field(default_factory=list)

    async def complete(self, messages, tools=()) -> Completion:
        self.seen.append(list(messages))
        self.tools_seen.append(tuple(schema.name for schema in tools))
        if not self.script:
            return reply("")
        return self.script.pop(0)

    async def stream(self, messages, tools=()):
        completion = await self.complete(messages, tools)
        yield completion.message.content
