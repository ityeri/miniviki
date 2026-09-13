from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from ..events import StreamEvent
from ..types import ClientTool, ContextInit


@runtime_checkable
class Transport(Protocol):
    """The second abstraction layer: how the semantics actually travel.

    http is the one we ship. ssh or a websocket would slot in here without the
    client, the server or any front noticing.
    """

    async def create_context(self, init: ContextInit) -> dict[str, Any]: ...
    async def context_state(self, context_id: str) -> dict[str, Any]: ...
    async def submit(self, context_id: str, text: str) -> dict[str, Any]: ...
    def subscribe(self, context_id: str, from_seq: int = 0) -> AsyncIterator[StreamEvent]: ...
    async def interrupt(self, context_id: str) -> dict[str, Any]: ...
    async def resolve_approval(
        self,
        context_id: str,
        call_id: str,
        decision: str
    ) -> dict[str, Any]: ...
    async def update_tools(self, context_id: str, tools: list[ClientTool]) -> dict[str, Any]: ...
    async def aclose(self) -> None: ...
