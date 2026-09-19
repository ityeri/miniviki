from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from miniviki.llm_interfaces.content import Context


class ToolChoiceMode(StrEnum):
    AUTO = 'auto'
    REQUIRED = 'required'
    NONE = 'none'


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    strict: bool = False


@dataclass(frozen=True)
class ToolChoice:
    mode: ToolChoiceMode = ToolChoiceMode.AUTO
    name: str | None = None
    # whitelist. empty means every declared tool is callable
    allowed: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReasoningRequest:
    effort: str | None = None
    budget: int | None = None
    visible: bool = False


@dataclass(frozen=True)
class Limits:
    max_output_tokens: int | None = None
    temperature: float | None = None
    top_p: float | None = None
    stop: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Request:
    model: str
    messages: Context = field(default_factory=list)
    instructions: str | None = None
    tools: list[ToolSpec] = field(default_factory=list)
    tool_choice: ToolChoice = field(default_factory=ToolChoice)
    limits: Limits = field(default_factory=Limits)
    reasoning: ReasoningRequest | None = None
    # provider specific knobs (safety settings, guards, cache handles). the
    # canonical layer never reads them
    provider_options: Mapping[str, Any] = field(default_factory=dict)
    # escape hatch for parameters that outrun this model
    extra: Mapping[str, Any] = field(default_factory=dict)
