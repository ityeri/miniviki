from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self


class EventKind(StrEnum):
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    COMPACT = "compact"
    BOUNDARY = "boundary"
    APPROVAL = "approval"


@dataclass(frozen=True, slots=True)
class ContextEvent:
    context_id: str
    seq: int
    kind: EventKind
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "seq": self.seq,
            "kind": str(self.kind),
            "payload": self.payload,
            "created_at": self.created_at
        }

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return ContextEvent(
            context_id=str(raw_data["context_id"]),
            seq=int(raw_data["seq"]),
            kind=EventKind(str(raw_data["kind"])),
            payload=dict(raw_data.get("payload") or {}),
            created_at=float(raw_data.get("created_at") or 0.0)
        )
