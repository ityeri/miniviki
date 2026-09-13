from collections.abc import Callable
from dataclasses import dataclass

from ..constants import DEFAULT_COMPACT_THRESHOLD, DEFAULT_CONTEXT_WINDOW
from ..errors import ContextError
from .event import ContextEvent, EventKind
from .log import EventLog
from .projection import latest_compact

PRESERVED_KINDS = (EventKind.BOUNDARY, EventKind.APPROVAL)
Summarizer = Callable[[list[ContextEvent]], str]


@dataclass(frozen=True, slots=True)
class CompactionPolicy:
    window_tokens: int = DEFAULT_CONTEXT_WINDOW
    threshold: float = DEFAULT_COMPACT_THRESHOLD

    def limit(self) -> int:
        return int(self.window_tokens * self.threshold)


def estimate_tokens(events: list[ContextEvent]) -> int:
    """Chars over four. Crude on purpose: the trigger only needs a cheap monotone signal."""
    total = 0
    for event in events:
        total += len(str(event.payload.get("content", "")))
        total += len(str(event.payload.get("summary", "")))
        for call in event.payload.get("calls", ()):
            total += len(str(call))
    return total // 4


def should_compact(events: list[ContextEvent], policy: CompactionPolicy) -> bool:
    return estimate_tokens(events) >= policy.limit()


def compact(
    log: EventLog,
    context_id: str,
    summarizer: Summarizer,
    policy: CompactionPolicy | None = None
) -> ContextEvent:
    """Fold the live window into one summary event.

    Boundary and approval events survive verbatim inside the payload: losing a
    toolset change or an unresolved approval to a paraphrase is exactly the kind
    of unrecoverable loss compaction is allowed to avoid.
    """
    events = log.read(context_id)
    if not events:
        raise ContextError(f"nothing to compact in {context_id}")
    marker = latest_compact(events)
    live = [event for event in events if marker is None or event.seq > marker.seq]
    if not live:
        raise ContextError(f"{context_id} has nothing new since the last compaction")
    summary = summarizer(live)
    return log.append(
        context_id,
        EventKind.COMPACT,
        {
            "summary": summary,
            "covered_until_seq": live[-1].seq,
            "preserved": [event.to_json() for event in live if event.kind in PRESERVED_KINDS],
            "estimated_tokens": estimate_tokens(live),
            "threshold": (policy or CompactionPolicy()).limit()
        }
    )
