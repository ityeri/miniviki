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


def project(events: list[ContextEvent], include_notes: bool = True) -> list[Message]:
    """Fold the log into the message list the model sees.

    A note that lands between an assistant message with tool calls and the tool
    results answering it is not allowed by any provider, and the log can easily
    put one there -- an approval or a toolset change is recorded before the tool
    it concerns finishes. So notes are held back until the tool exchange closes.
    """
    start = 0
    summary = ""
    for index, event in enumerate(events):
        if event.kind is EventKind.COMPACT:
            start = index + 1
            summary = str(event.payload.get("summary", ""))
    messages: list[Message] = []
    if summary:
        messages.append(Message(role="system", content=f"[compacted] {summary}"))
    deferred: list[Message] = []
    awaiting = 0
    for event in events[start:]:
        if event.kind is EventKind.TOOL_CALL:
            message = message_for(event)
            if message is not None:
                messages.append(message)
                awaiting = len(event.payload.get("calls", ()))
            continue
        if event.kind is EventKind.TOOL_RESULT:
            message = message_for(event)
            if message is not None:
                messages.append(message)
            awaiting = max(0, awaiting - 1)
            if awaiting == 0:
                messages.extend(deferred)
                deferred.clear()
            continue
        message = message_for(event)
        if message is None:
            continue
        if awaiting > 0:
            deferred.append(message)
        elif include_notes:
            messages.append(message)
    messages.extend(deferred)
    return messages
