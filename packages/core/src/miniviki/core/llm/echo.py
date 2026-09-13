from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from .types import Completion, Message, ToolSchema


def last_user_text(messages: Sequence[Message]) -> str:
    for message in reversed(list(messages)):
        if message.role == "user":
            return message.content
    return ""


@dataclass(slots=True)
class EchoClient:
    """A dev client that answers with the last user message.

    It exists so the whole path -- transport, event log, projection, sse -- can be
    exercised end to end with no key and no network call.
    """

    prefix: str = "echo: "

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema] = ()
    ) -> Completion:
        return Completion(
            message=Message(role="assistant", content=self.prefix + last_user_text(messages))
        )

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema] = ()
    ) -> AsyncIterator[str]:
        yield self.prefix + last_user_text(messages)
