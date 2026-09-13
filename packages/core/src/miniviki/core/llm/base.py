from collections.abc import AsyncIterator, Sequence
from typing import Protocol, runtime_checkable

from .types import Completion, Message, ToolSchema


@runtime_checkable
class LLMClient(Protocol):
    """Deliberately tiny: messages plus tool schemas in, completion out.

    Streaming and usage accounting are part of the contract, not extras -- both
    are needed to run this on a server and to know what it costs.
    """

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema] = ()
    ) -> Completion: ...

    def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[ToolSchema] = ()
    ) -> AsyncIterator[str]: ...
