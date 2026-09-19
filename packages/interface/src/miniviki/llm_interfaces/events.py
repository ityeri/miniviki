from dataclasses import dataclass, field
from typing import Any

from miniviki.llm_interfaces.response import StopReason, Usage


@dataclass(frozen=True)
class Queued:
    pass


@dataclass(frozen=True)
class Started:
    response_id: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class InProgress:
    response_id: str | None = None


@dataclass(frozen=True)
class BlockStarted:
    # index identifies the block inside this turn. block level events are the
    # only way to follow a turn that produces text and tool calls at once
    index: int
    kind: str
    call_id: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class TextDelta:
    index: int
    text: str


@dataclass(frozen=True)
class ArgsDelta:
    index: int
    fragment: str


@dataclass(frozen=True)
class ReasoningDelta:
    index: int
    text: str


@dataclass(frozen=True)
class SignatureDelta:
    index: int
    opaque: bytes


@dataclass(frozen=True)
class BlockStopped:
    index: int


@dataclass(frozen=True)
class UsageReported:
    usage: Usage


@dataclass(frozen=True)
class Completed:
    stop_reason: StopReason = StopReason.UNKNOWN
    raw_stop_reason: str = ''
    response_id: str | None = None


@dataclass(frozen=True)
class Failed:
    code: str
    message: str = ''
    retryable: bool = False


@dataclass(frozen=True)
class ProviderEvent:
    # provider events that this model does not describe, passed through so a
    # stream consumer can still observe them
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


type StreamEvent = (
        Queued
        | Started
        | InProgress
        | BlockStarted
        | TextDelta
        | ArgsDelta
        | ReasoningDelta
        | SignatureDelta
        | BlockStopped
        | UsageReported
        | Completed
        | Failed
        | ProviderEvent
)
