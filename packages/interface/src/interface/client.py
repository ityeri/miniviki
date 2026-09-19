from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol, runtime_checkable

from interface.capabilities import Capabilities
from interface.errors import InterfaceError
from interface.events import StreamEvent
from interface.request import Request
from interface.response import Completion


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

    def lower_request(self, request: Request) -> Mapping[str, Any]: ...

    def parse_completion(self, payload: Mapping[str, Any]) -> Completion: ...

    def parse_event(self, payload: Mapping[str, Any]) -> StreamEvent: ...

    def parse_error(self, status: int, payload: Mapping[str, Any]) -> InterfaceError: ...
