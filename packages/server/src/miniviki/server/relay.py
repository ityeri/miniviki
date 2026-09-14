"""The server side of a call that runs on the client's machine.

The request is a log event, so delivering it is a replay rather than a push: a
client that reconnects with `from_seq` finds whatever it has not answered yet.
That keeps the log the only place this state lives -- and it means every function
here has to be safe to run twice, because a replay makes that likely rather than
possible.
"""

from typing import Any

from miniviki.core.context import EventKind, EventLog

from .errors import UnknownClientRequest


def pending_requests(log: EventLog, context_id: str) -> list[dict[str, Any]]:
    """Client calls with no result yet, oldest first."""
    answered = _answered(log, context_id)
    return [
        request
        for request in _announced(log, context_id)
        if request.get("call_id") not in answered
    ]


def record_result(log: EventLog, context_id: str, call_id: str, content: str) -> bool:
    """Turn the client's answer into a tool result.

    Returns True only for the write that actually resolved the call. A client that
    reconnected may answer something it already answered; that second write is
    dropped, because resolving one call twice would drive the run an extra turn.
    """
    announced = _announced(log, context_id, call_id)
    if not announced:
        raise UnknownClientRequest(
            f"no client call is pending with id {call_id!r} on {context_id}"
        )
    if call_id in _answered(log, context_id):
        return False
    log.append(
        context_id,
        EventKind.TOOL_RESULT,
        {
            "call_id": call_id,
            "name": str(announced[-1].get("tool", "")),
            "content": content,
            "relayed": True
        }
    )
    return True


def _announced(log: EventLog, context_id: str, call_id: str | None = None) -> list[dict[str, Any]]:
    return [
        dict(event.payload)
        for event in log.read(context_id)
        if event.kind is EventKind.TOOL_REQUEST
        and (call_id is None or event.payload.get("call_id") == call_id)
    ]


def _answered(log: EventLog, context_id: str) -> set[Any]:
    return {
        event.payload.get("call_id")
        for event in log.read(context_id)
        if event.kind is EventKind.TOOL_RESULT
    }
