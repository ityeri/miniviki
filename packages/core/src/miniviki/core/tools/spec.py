import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..constants import DEFAULT_MAX_RESULT_CHARS
from ..errors import ToolError
from ..llm import ToolSchema

ToolHandler = Callable[..., Awaitable[str]]
TOOL_NAME_SEPARATOR = "_"
TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_tool_name(name: str) -> str:
    """Tool names are wire identifiers, so the provider's rule is enforced here.

    Every provider accepts `^[a-zA-Z0-9_-]+$` and nothing else. A colon or a dot
    comes back as a 400 at request time, which surfaces to the user as a run that
    died for no visible reason. So the contract is checked at construction.
    """
    if not name:
        raise ToolError("tool name must not be empty")
    if not TOOL_NAME_PATTERN.fullmatch(name):
        raise ToolError(
            f"tool name {name!r} must match {TOOL_NAME_PATTERN.pattern}:"
            " letters, digits, underscore and hyphen only"
        )
    return name


def namespace_of(name: str) -> str:
    """`client_shell` -> `client`; a bare `exec` has no namespace."""
    head, separator, _ = name.partition(TOOL_NAME_SEPARATOR)
    return head if separator else ""


@dataclass(frozen=True, slots=True)
class ToolResult:
    content: str
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """A callable capability plus the budget and consent it needs.

    The handler is deliberately outside the fingerprint: two toolsets that differ
    only in implementation are the same toolset as far as the model is concerned,
    which is what keeps prompt caching honest. `client_tool` is out for the same
    reason -- the model sees `client_shell`, never whatever the client calls it.
    """

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    handler: ToolHandler | None = None
    max_result_chars: int = DEFAULT_MAX_RESULT_CHARS
    requires_approval: bool = False
    client_scoped: bool = False
    client_tool: str = ""

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
