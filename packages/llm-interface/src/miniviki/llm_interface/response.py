from dataclasses import dataclass
from enum import StrEnum

from miniviki.llm_interface.content import Turn


class StopReason(StrEnum):
    END_TURN = 'end_turn'
    TOOL_USE = 'tool_use'
    MAX_TOKENS = 'max_tokens'
    STOP_SEQUENCE = 'stop_sequence'
    CONTENT_FILTER = 'content_filter'
    CANCELLED = 'cancelled'
    ERROR = 'error'
    UNKNOWN = 'unknown'


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cached_read_tokens: int = 0
    cached_write_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass(frozen=True)
class Completion:
    # the assistant turn as a context ready value. appending it to the next
    # request context is the caller's job
    turn: Turn
    stop_reason: StopReason = StopReason.UNKNOWN
    # provider wording kept as received for logs and debugging
    raw_stop_reason: str = ''
    usage: Usage = Usage()
    response_id: str | None = None
    model: str | None = None
