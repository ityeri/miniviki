import hashlib
from dataclasses import dataclass, field
from typing import Any

from ..tools import Toolset
from .env import render_environment
from .soul import SoulLayer, merge_souls


@dataclass(frozen=True, slots=True)
class InitialContext:
    """The assembled artifact. The digest is what gets pinned, cache-shared and diffed."""

    text: str
    digest: str
    sections: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


def render_index(title: str, entries: list[str]) -> str:
    """Index only.

    Bodies are fetched on demand -- loading every skill up front kills extensibility.
    """
    if not entries:
        return ""
    lines = [f"# {title}", "", "Load one with the matching tool when it becomes relevant:"]
    lines.extend(f"- {entry}" for entry in sorted(entries))
    return "\n".join(lines)


def _memory_section(memory_summary: str) -> str:
    body = memory_summary.strip()
    return f"# Memory summary\n\n{body}" if body else ""


def assemble(
    souls: list[SoulLayer],
    toolset: Toolset,
    skill_index: list[str] | None = None,
    memory_summary: str = "",
    extra_sections: list[str] | None = None
) -> InitialContext:
    sections = [
        ("soul", merge_souls(souls)),
        ("environment", render_environment(toolset)),
        ("skills", render_index("Skills", skill_index or [])),
        ("memory", _memory_section(memory_summary)),
        ("extra", "\n\n".join(extra_sections or []))
    ]
    text = "\n\n".join(body for _, body in sections if body.strip())
    return InitialContext(
        text=text,
        digest=hashlib.sha256(text.encode("utf-8")).hexdigest()[:12],
        sections=tuple(name for name, body in sections if body.strip()),
        metadata={"toolset_version": toolset.version}
    )
