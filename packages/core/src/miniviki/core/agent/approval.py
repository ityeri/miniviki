from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..errors import ApprovalRequired


class Decision(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    call_id: str
    tool: str
    arguments: dict[str, Any] = field(default_factory=dict)
    decision: Decision = Decision.PENDING


@dataclass(slots=True)
class ApprovalGate:
    """A run stops at a dangerous call and waits for a human.

    Nothing dangerous runs on a timeout or a default: an unanswered request stays
    PENDING and the run stays parked.
    """

    requests: dict[str, ApprovalRequest] = field(default_factory=dict)

    def request(self, call_id: str, tool: str, arguments: dict[str, Any]) -> ApprovalRequest:
        record = ApprovalRequest(call_id=call_id, tool=tool, arguments=dict(arguments))
        self.requests[call_id] = record
        return record

    def check(self, call_id: str) -> Decision:
        record = self.requests.get(call_id)
        return record.decision if record is not None else Decision.PENDING

    def resolve(self, call_id: str, decision: Decision) -> ApprovalRequest:
        record = self.requests.get(call_id)
        if record is None:
            raise ApprovalRequired(f"no approval request is pending for {call_id}")
        updated = ApprovalRequest(
            call_id=record.call_id,
            tool=record.tool,
            arguments=record.arguments,
            decision=decision
        )
        self.requests[call_id] = updated
        return updated

    def pending(self) -> list[ApprovalRequest]:
        return [item for item in self.requests.values() if item.decision is Decision.PENDING]

    def forget(self, call_id: str) -> None:
        self.requests.pop(call_id, None)
