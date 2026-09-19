from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any, Protocol, runtime_checkable

from miniviki.llm_interfaces.capabilities import Capabilities
from miniviki.llm_interfaces.errors import InterfaceError
from miniviki.llm_interfaces.events import StreamEvent
from miniviki.llm_interfaces.request import Request
from miniviki.llm_interfaces.response import Completion


@runtime_checkable
class LLMClient(Protocol):
    """canonical request in, completion or block level event stream out"""

    async def capabilities(self) -> Capabilities: ...

    async def complete(self, request: Request) -> Completion: ...

    def stream(self, request: Request) -> AsyncIterator[StreamEvent]: ...


@runtime_checkable
class ProviderAdapter(Protocol):
    """translation between the canonical model and one provider wire format.

    adapters are pure and stateless. context ownership, appending a response
    to the next request and compaction all stay in the client loop
    """

    def capabilities(self) -> Capabilities: ...

    def lower_request(self, request: Request, stream: bool = False) -> Mapping[str, Any]: ...

    def parse_completion(self, payload: Mapping[str, Any]) -> Completion: ...

    # one wire chunk can carry several blocks at once (parallel tool calls
    # arrive as separate entries of the same delta), so this returns a sequence
    def parse_event(self, payload: Mapping[str, Any]) -> Sequence[StreamEvent]: ...

    def parse_error(self, status: int, payload: Mapping[str, Any]) -> InterfaceError: ...
