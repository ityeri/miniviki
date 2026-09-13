from dataclasses import dataclass, field
from typing import Any, Self

from .capability import ClientCapability


@dataclass(frozen=True, slots=True)
class ClientTool:
    """A tool that only exists while this client is attached, under `client:`."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "parameters": self.parameters}

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return ClientTool(
            name=str(raw_data["name"]),
            description=str(raw_data.get("description", "")),
            parameters=dict(raw_data.get("parameters") or {})
        )


@dataclass(frozen=True, slots=True)
class ContextInit:
    kind: str = "main"
    parent_id: str | None = None
    label: str = ""
    soul_ref: str | None = None
    capabilities: ClientCapability = field(default_factory=ClientCapability)
    tools: tuple[ClientTool, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "parent_id": self.parent_id,
            "label": self.label,
            "soul_ref": self.soul_ref,
            "capabilities": self.capabilities.to_json(),
            "tools": [tool.to_json() for tool in self.tools]
        }


@dataclass(frozen=True, slots=True)
class ContextHandle:
    id: str
    kind: str = "main"
    toolset_version: str = ""
    initial_context_digest: str = ""
    label: str = ""

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return ContextHandle(
            id=str(raw_data["id"]),
            kind=str(raw_data.get("kind", "main")),
            toolset_version=str(raw_data.get("toolset_version", "")),
            initial_context_digest=str(raw_data.get("initial_context_digest", "")),
            label=str(raw_data.get("label", ""))
        )


@dataclass(frozen=True, slots=True)
class Turn:
    text: str
    status: str
    events: tuple[Any, ...] = ()
    run_id: str = ""

    @property
    def needs_approval(self) -> bool:
        return self.status == "waiting_approval"
