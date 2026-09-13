import hashlib
from dataclasses import dataclass

from ..errors import ToolNotFound, ToolsetFrozen
from ..llm import ToolSchema
from .spec import ToolSpec

_UNCHANGED_LIMIT = 12


@dataclass(frozen=True, slots=True)
class ToolsetDiff:
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    unchanged: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not self.added and not self.removed

    def render(
        self,
        version_from: str,
        version_to: str,
        from_label: str = "",
        to_label: str = ""
    ) -> str:
        """The block the agent actually reads at a toolset boundary."""
        attributes = [f'version="{version_from}->{version_to}"']
        if from_label or to_label:
            attributes.append(f'from="{from_label}" to="{to_label}"')
        lines = [f"<toolset_change {' '.join(attributes)}>"]
        lines.extend(f"  + {name}" for name in self.added)
        lines.extend(f"  - {name} (no longer callable)" for name in self.removed)
        if self.unchanged:
            sample = list(self.unchanged[:_UNCHANGED_LIMIT])
            extra = len(self.unchanged) - _UNCHANGED_LIMIT
            suffix = "" if extra <= 0 else f" (+{extra} more)"
            lines.append(f"  = {', '.join(sample)}{suffix}   unchanged")
        lines.append("</toolset_change>")
        return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class Toolset:
    """A frozen snapshot. Changing it means taking a new one, never editing this one."""

    version: str
    specs: tuple[ToolSpec, ...] = ()
    client_label: str = ""

    @classmethod
    def from_specs(cls, specs: list[ToolSpec], client_label: str = "") -> Toolset:
        ordered = tuple(sorted(specs, key=lambda spec: spec.name))
        joined = "\n".join(spec.fingerprint() for spec in ordered)
        digest = hashlib.sha256(joined.encode("utf-8"))
        return cls(version=digest.hexdigest()[:12], specs=ordered, client_label=client_label)

    def names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.specs)

    def get(self, name: str) -> ToolSpec:
        for spec in self.specs:
            if spec.name == name:
                return spec
        raise ToolNotFound(name)

    def schemas(self) -> list[ToolSchema]:
        return [spec.schema() for spec in self.specs]

    def digest(self) -> str:
        return self.version

    def diff(self, other: Toolset) -> ToolsetDiff:
        mine = set(self.names())
        theirs = set(other.names())
        return ToolsetDiff(
            added=tuple(sorted(theirs.difference(mine))),
            removed=tuple(sorted(mine.difference(theirs))),
            unchanged=tuple(sorted(mine.intersection(theirs)))
        )

    def frozen_error(self) -> ToolsetFrozen:
        return ToolsetFrozen(
            f"toolset {self.version} is pinned; take a new snapshot at a boundary"
            " instead of editing it"
        )
