from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    USER = 'user'
    ASSISTANT = 'assistant'


class MediaKind(StrEnum):
    IMAGE = 'image'
    AUDIO = 'audio'
    VIDEO = 'video'
    FILE = 'file'


@dataclass(frozen=True)
class Text:
    # cache_breakpoint marks an input side prompt cache boundary. it is a
    # request side hint only, providers that cache automatically ignore it
    text: str
    cache_breakpoint: bool = False


@dataclass(frozen=True)
class Media:
    kind: MediaKind
    media_type: str
    data: bytes | None = None
    url: str | None = None


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    # models are not guaranteed to emit valid json and some providers stream
    # arguments as fragments, so the text as received is kept alongside
    args_raw: str | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: list[Block] = field(default_factory=list)
    is_error: bool = False


@dataclass(frozen=True)
class Reasoning:
    # text is the readable part. opaque carries the provider signature or
    # encrypted blob and has to be sent back verbatim on the next turn
    text: str | None = None
    opaque: bytes | None = None


@dataclass(frozen=True)
class ServerTool:
    # a tool the provider runs on its own side. kept opaque on purpose, its
    # semantics belong to the provider
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Unknown:
    # anything this model does not describe. preserved so that a round trip
    # cannot silently drop provider specific items
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)


type Block = Text | Media | ToolCall | ToolResult | Reasoning | ServerTool | Unknown


@dataclass(frozen=True)
class Turn:
    role: Role
    blocks: list[Block] = field(default_factory=list)
