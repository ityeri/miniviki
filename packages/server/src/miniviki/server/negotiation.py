from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from miniviki.core.tools import CLIENT_NAMESPACE, Toolset, ToolSpec
from miniviki.mca import ClientCapability, ClientTool

RELAY_GAP = (
    "error: {name} is a client tool and this build has no relay for it yet. "
    "Run the same step with `exec` inside the workspace instead."
)


@dataclass(frozen=True, slots=True)
class Negotiation:
    """The result of capability negotiation.

    Capabilities only ever subtract. A client that declares nothing gets less,
    never more, and every removal is recorded so it can be explained.
    """

    toolset: Toolset
    dropped: tuple[str, ...] = ()

    def summary(self) -> str:
        if not self.dropped:
            return "every requested capability was granted"
        return "; ".join(self.dropped)


def qualify(name: str) -> str:
    if name.startswith(f"{CLIENT_NAMESPACE}:"):
        return name
    return f"{CLIENT_NAMESPACE}:{name}"


def client_specs(client_tools: Sequence[ClientTool]) -> list[ToolSpec]:
    specs: list[ToolSpec] = []
    for tool in client_tools:
        name = qualify(tool.name)
        specs.append(
            ToolSpec(
                name=name,
                description=tool.description or f"client tool {name}",
                parameters=tool.parameters or {"type": "object", "properties": {}},
                handler=_unrelayed(name)
            )
        )
    return specs


def _unrelayed(name: str):
    async def run(**_arguments: Any) -> str:
        return RELAY_GAP.format(name=name)

    return run


def negotiate(
    base: Sequence[ToolSpec],
    client_tools: Sequence[ClientTool],
    capabilities: ClientCapability
) -> Negotiation:
    kept: list[ToolSpec] = list(base)
    dropped: list[str] = []
    taken = {spec.name for spec in base}
    for spec in client_specs(client_tools):
        if spec.name in taken:
            dropped.append(f"{spec.name}: a tool of that name already exists on this context")
            continue
        if spec.requires_approval and not capabilities.approval_ui:
            dropped.append(f"{spec.name}: requires approval but the client declared no approval ui")
            continue
        taken.add(spec.name)
        kept.append(spec)
    if not capabilities.approval_ui:
        kept = [spec for spec in kept if not spec.requires_approval]
        dropped += [
            f"{spec.name}: requires approval but the client declared no approval ui"
            for spec in base
            if spec.requires_approval
        ]
    return Negotiation(toolset=Toolset.from_specs(kept), dropped=tuple(dropped))
