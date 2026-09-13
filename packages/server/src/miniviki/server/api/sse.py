import json

from miniviki.core.context import ContextEvent, EventKind
from miniviki.mca import (
    APPROVAL_REQUEST,
    BOUNDARY,
    MESSAGE,
    RUN_END,
    TOOL_CALL,
    TOOL_RESULT,
    StreamEvent,
)

WIRE_KIND = {
    EventKind.MESSAGE: MESSAGE,
    EventKind.TOOL_CALL: TOOL_CALL,
    EventKind.TOOL_RESULT: TOOL_RESULT,
    EventKind.BOUNDARY: BOUNDARY,
    EventKind.APPROVAL: APPROVAL_REQUEST,
    EventKind.RUN_END: RUN_END
}


def to_wire(event: ContextEvent) -> StreamEvent | None:
    """Context events are the truth; wire events are a projection of them.

    A compact event has no wire form on purpose -- it is bookkeeping, and the
    client already has the conversation.
    """
    kind = WIRE_KIND.get(event.kind)
    if kind is None:
        return None
    payload = dict(event.payload)
    if event.kind is EventKind.APPROVAL:
        payload.setdefault("status", "waiting_approval")
    return StreamEvent(seq=event.seq, kind=kind, payload=payload)


def format_sse(event: StreamEvent) -> str:
    return f"data: {json.dumps(event.to_json(), ensure_ascii=False)}\n\n"
