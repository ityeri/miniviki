from collections.abc import AsyncIterator, Mapping
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class TransportResponse(Protocol):
    """one http response. json body for the unary path, chunks for the stream"""

    @property
    def status(self) -> int: ...

    async def json(self) -> Mapping[str, Any]: ...

    def chunks(self) -> AsyncIterator[bytes]: ...


@runtime_checkable
class Transport(Protocol):
    """the only seam where this package touches the network.

    implementations own connection pooling, proxies, timeouts and retries
    """

    async def post(
        self, url: str, headers: Mapping[str, str], body: Mapping[str, Any]
    ) -> TransportResponse: ...
