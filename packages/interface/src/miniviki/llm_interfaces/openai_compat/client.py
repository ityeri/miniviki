from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field

from miniviki.llm_interfaces.capabilities import Capabilities
from miniviki.llm_interfaces.events import StreamEvent
from miniviki.llm_interfaces.openai_compat.adapter import ChatCompletionsAdapter
from miniviki.llm_interfaces.openai_compat.sse import sse_payloads
from miniviki.llm_interfaces.request import Request
from miniviki.llm_interfaces.response import Completion
from miniviki.llm_interfaces.transport import Transport

_BAD_REQUEST = 400
_CHAT_COMPLETIONS_PATH = '/chat/completions'


@dataclass(frozen=True)
class OpenAIChatClient:
    """LLMClient over the chat completions wire format.

    base_url selects the deployment, so one client covers openai, deepseek,
    groq, together, openrouter, xai and any local server that speaks the same
    shape
    """

    transport: Transport
    adapter: ChatCompletionsAdapter = field(default_factory=ChatCompletionsAdapter)
    base_url: str = 'https://api.openai.com/v1'
    api_key: str | None = None
    extra_headers: Mapping[str, str] = field(default_factory=dict)

    async def capabilities(self) -> Capabilities:
        return self.adapter.capabilities()

    async def complete(self, request: Request) -> Completion:
        response = await self.transport.post(
            self._url(), self._headers(), self.adapter.lower_request(request)
        )
        payload = await response.json()
        if response.status >= _BAD_REQUEST:
            raise self.adapter.parse_error(response.status, payload)
        return self.adapter.parse_completion(payload)

    def stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        return self._stream(request)

    async def _stream(self, request: Request) -> AsyncIterator[StreamEvent]:
        response = await self.transport.post(
            self._url(), self._headers(), self.adapter.lower_request(request, stream=True)
        )
        if response.status >= _BAD_REQUEST:
            raise self.adapter.parse_error(response.status, await response.json())
        async for payload in sse_payloads(response.chunks()):
            for event in self.adapter.parse_event(payload):
                yield event

    def _url(self) -> str:
        return f'{self.base_url.rstrip("/")}{_CHAT_COMPLETIONS_PATH}'

    def _headers(self) -> Mapping[str, str]:
        headers: dict[str, str] = {'content-type': 'application/json'}
        if self.api_key is not None:
            headers['authorization'] = f'Bearer {self.api_key}'
        headers.update(self.extra_headers)
        return headers
