from ..llm import Message, ToolCall
from .event import ContextEvent, EventKind


def message_for(event: ContextEvent) -> Message | None:
    """One log event -> at most one model message. COMPACT events carry no message of their own."""
    if event.kind is EventKind.MESSAGE:
        return Message(
            role=str(event.payload.get("role", "user")),
            content=str(event.payload.get("content", ""))
        )
    if event.kind is EventKind.TOOL_CALL:
        calls = tuple(ToolCall.from_json(raw) for raw in event.payload.get("calls", ()))
        return Message(
            role="assistant",
            content=str(event.payload.get("content", "")),
            tool_calls=calls
        )
    if event.kind is EventKind.TOOL_RESULT:
        return Message(
            role="tool",
            content=str(event.payload.get("content", "")),
            tool_call_id=str(event.payload.get("call_id", "")),
            name=str(event.payload.get("name", ""))
        )
    if event.kind in (EventKind.BOUNDARY, EventKind.APPROVAL):
        text = str(event.payload.get("text", ""))
        return Message(role="system", content=text) if text else None
    return None


def latest_compact(events: list[ContextEvent]) -> ContextEvent | None:
    found: ContextEvent | None = None
    for event in events:
        if event.kind is EventKind.COMPACT:
            found = event
    return found


def project(events: list[ContextEvent]) -> list[Message]:
    """Fold the log into what the model sees.

    A COMPACT event supersedes everything before it, so we resume from the
    newest marker and keep the raw events after it. The superseded events are
    still in the log -- superseded is not deleted.
    """
    marker = latest_compact(events)
    summary = str(marker.payload.get("summary", "")) if marker else ""
    tail = [event for event in events if marker is None or event.seq > marker.seq]
    messages: list[Message] = []
    if summary:
        messages.append(Message(role="system", content=f"[compacted] {summary}"))
    for event in tail:
        message = message_for(event)
        if message is not None:
            messages.append(message)
    return messages
