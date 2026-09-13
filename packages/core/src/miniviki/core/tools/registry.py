from dataclasses import dataclass, field

from ..errors import ToolError, ToolNotFound
from .spec import ToolSpec, validate_tool_name

CLIENT_NAMESPACE = "client"


@dataclass(slots=True)
class ToolRegistry:
    """Registration plus two naming laws.

    Names are unique, and only client tools live in the `client_` namespace.
    """

    reserved_namespaces: tuple[str, ...] = (CLIENT_NAMESPACE,)
    specs: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> ToolSpec:
        validate_tool_name(spec.name)
        if spec.name in self.specs:
            raise ToolError(f"tool {spec.name!r} is already registered")
        if spec.client_scoped and spec.namespace != CLIENT_NAMESPACE:
            raise ToolError(
                f"client scoped tool {spec.name!r} must live under {CLIENT_NAMESPACE}_"
            )
        if not spec.client_scoped and spec.namespace in self.reserved_namespaces:
            raise ToolError(
                f"tool {spec.name!r} cannot squat the reserved namespace {spec.namespace!r}"
            )
        self.specs[spec.name] = spec
        return spec

    def unregister(self, name: str) -> None:
        if name not in self.specs:
            raise ToolNotFound(name)
        del self.specs[name]

    def get(self, name: str) -> ToolSpec:
        try:
            return self.specs[name]
        except KeyError as error:
            raise ToolNotFound(name) from error

    def names(self) -> list[str]:
        return sorted(self.specs)

    def with_client_tools(self, specs: list[ToolSpec]) -> ToolRegistry:
        """Client tools get their own registry, so a dropped client drops exactly its own tools."""
        merged = dict(self.specs)
        for spec in specs:
            validate_tool_name(spec.name)
            if spec.namespace != CLIENT_NAMESPACE:
                raise ToolError(f"injected tool {spec.name!r} must live under {CLIENT_NAMESPACE}_")
            if spec.name in merged:
                raise ToolError(f"injected tool {spec.name!r} collides with an existing tool")
            merged[spec.name] = spec
        return ToolRegistry(reserved_namespaces=self.reserved_namespaces, specs=merged)
