from ...index import KVSearchIndex
from ...kv import VersionedKVStore
from ..spec import ToolSpec
from .kv import build_kv_tools

SKILL_GUIDANCE = (
    "A skill is a reusable procedure, not a diary entry: capture the generalisable rule "
    "and why it holds."
)


def build_skill_tools(
    store: VersionedKVStore,
    index: KVSearchIndex | None = None
) -> list[ToolSpec]:
    return build_kv_tools(store, "skill", index=index, guidance=SKILL_GUIDANCE)
