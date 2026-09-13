from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..constants import DEFAULT_MAX_RESULT_CHARS, NAMESPACE_SEPARATOR
from ..errors import ToolError
from ..llm import ToolSchema

ToolHandler = Callable[..., Awaitable[str]]
_FORBIDDEN_CHARS = {".", "/", "\\", "\x00", " ", "\t", "\n", "\r"}


def validate_tool_name(name: str) -> str:
    """Tool names use the same `word:word` notation as keys. No dots, no paths."""
    if not name:
        raise ToolError("tool name must not be empty")
    if name.startswith(NAMESPACE_SEPARATOR) or name.endswith(NAMESPACE_SEPARATOR):
        raise ToolError(f"tool name must not start or end with {NAMESPACE_SEPARATOR!r}")
    for char in name:
        if char in _FORBIDDEN_CHARS:
            raise ToolError(f"tool name {name!r} contains a forbidden character: {char!r}")
    for segment in name.split(NAMESPACE_SEPARATOR):
        if not segment:
            raise ToolError(f"tool name {name!r} contains an empty segment")
        if not all(char.isalnum() or char in {"_", "-"} for char in segment):
            raise ToolError(f"tool name segment {segment!r} is not a plain word")
    return name


def namespace_of(name: str) -> str:
    """`client:shell` -> `client`; a bare `exec` has no namespace."""
    head, _, _ = name.partition(NAMESPACE_SEPARATOR)
    return head if head != name else ""


@dataclass(frozen=True, slots=True)
class ToolResult:
    content: str
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A callable capability plus the budget and consent it needs.

    The handler is deliberately outside the fingerprint: two toolsets that differ
    only in implementation are the same toolset as far as the model is concerned,
    which is what keeps prompt caching honest.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: ToolHandler | None = None
    max_result_chars: int = DEFAULT_MAX_RESULT_CHARS
    requires_approval: bool = False
    client_scoped: bool = False

    @property
    def namespace(self) -> str:
        return namespace_of(self.name)

    def fingerprint(self) -> str:
        return repr(
            (
                self.name,
                self.description,
                sorted(self.parameters.items()),
                self.max_result_chars,
                self.requires_approval,
                self.client_scoped
            )
        )

    def schema(self) -> ToolSchema:
        return ToolSchema(name=self.name, description=self.description, parameters=self.parameters)

    def apply_budget(self, text: str) -> ToolResult:
        """Trim to the spec budget.

        The budget lives on the spec, not in dispatch: trimming after the fact loses
        data we never got to look at.
        """
        if len(text) <= self.max_result_chars:
            return ToolResult(content=text)
        head = text[: self.max_result_chars]
        return ToolResult(
            content=f"{head}\n[truncated: {len(text) - self.max_result_chars} more characters]",
            truncated=True
        )
