import codecs
import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

_DONE = '[DONE]'


async def sse_payloads(chunks: AsyncIterator[bytes]) -> AsyncIterator[Mapping[str, Any]]:
    # event-stream framing belongs to the transport side of the boundary, so it
    # sits next to the client. only data fields carry the json this adapter
    # understands; comments, event names and blank lines are dropped
    decoder = codecs.getincrementaldecoder('utf-8')()
    buffer = ''
    async for chunk in chunks:
        buffer += decoder.decode(chunk)
        while '\n' in buffer:
            line, buffer = buffer.split('\n', 1)
            line = line.strip()
            if not line.startswith('data:'):
                continue
            data = line[5:].strip()
            if data == _DONE:
                return
            yield json.loads(data)
