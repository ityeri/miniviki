from ...index import KVSearchIndex
from ...kv import VersionedKVStore
from ..spec import ToolSpec
from .kv import build_kv_tools

MEMORY_GUIDANCE = "Write facts that will still matter next week, not a log of what just happened."


def build_memory_tools(
    store: VersionedKVStore,
    index: KVSearchIndex | None = None
) -> list[ToolSpec]:
    return build_kv_tools(store, "memory", index=index, guidance=MEMORY_GUIDANCE)
