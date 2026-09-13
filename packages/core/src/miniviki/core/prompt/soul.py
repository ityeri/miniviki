from dataclasses import dataclass
from pathlib import Path

GLOBAL_LAYER = "global"
AGENT_LAYER = "agent"
CONTEXT_LAYER = "context"
LAYER_ORDER = (GLOBAL_LAYER, AGENT_LAYER, CONTEXT_LAYER)


@dataclass(frozen=True, slots=True)
class SoulLayer:
    name: str
    body: str = ""


def load_soul_layer(name: str, path: str | Path | None) -> SoulLayer:
    if path is None:
        return SoulLayer(name=name)
    candidate = Path(path)
    if not candidate.is_file():
        return SoulLayer(name=name)
    return SoulLayer(name=name, body=candidate.read_text(encoding="utf-8"))


def merge_souls(layers: list[SoulLayer]) -> str:
    """Concat, not override.

    Free prose has no keys, so there is nothing to override yet. Section headings
    are the sanctioned upgrade path: once every layer uses them, a section can be
    replaced instead of appended without touching anything else.
    """
    blocks = []
    for layer in sorted(layers, key=lambda item: _order_of(item.name)):
        body = layer.body.strip()
        if body:
            blocks.append(f"<!-- soul:{layer.name} -->\n{body}")
    return "\n\n".join(blocks)


def _order_of(name: str) -> int:
    try:
        return LAYER_ORDER.index(name)
    except ValueError:
        return len(LAYER_ORDER)
