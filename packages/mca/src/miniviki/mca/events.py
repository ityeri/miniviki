from dataclasses import dataclass, field
from typing import Any, Self

MESSAGE = "message"
TOOL_CALL = "tool_call"
TOOL_RESULT = "tool_result"
BOUNDARY = "boundary"
APPROVAL_REQUEST = "approval_request"
RUN_END = "run_end"
STATUS = "status"

TERMINAL_KINDS = (RUN_END, APPROVAL_REQUEST)


@dataclass(frozen=True, slots=True)
class StreamEvent:
    seq: int
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.kind in TERMINAL_KINDS

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return StreamEvent(
            seq=int(raw_data.get("seq", 0)),
            kind=str(raw_data.get("kind", "")),
            payload=dict(raw_data.get("payload") or {})
        )

    def to_json(self) -> dict[str, Any]:
        return {"seq": self.seq, "kind": self.kind, "payload": self.payload}
