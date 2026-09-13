from ...index import KVSearchIndex
from ...kv import VersionedKVStore
from ..spec import ToolSpec


def _parameters(**properties: dict) -> dict:
    required = [name for name, spec in properties.items() if spec.pop("_required", False)]
    return {"type": "object", "properties": properties, "required": required}


def build_kv_tools(
    store: VersionedKVStore,
    namespace: str,
    index: KVSearchIndex | None = None,
    guidance: str = ""
) -> list[ToolSpec]:
    """One family of tools per store, all in the store's own namespace.

    Progressive disclosure is the contract here: `list` returns the index, `view`
    fetches a body on demand. Nothing inlines every body up front.
    """

    def name(action: str) -> str:
        return f"{namespace}:{action}"

    async def list_keys(prefix: str = "") -> str:
        keys = store.keys(prefix)
        if not keys:
            return f"no keys under {prefix!r}" if prefix else "the store is empty"
        return "\n".join(keys)

    async def view(key: str) -> str:
        return store.read(key)

    async def write(key: str, body: str, note: str = "") -> str:
        rev = store.write(key, body, trailer=note)
        return f"wrote {key} at revision {rev}"

    async def patch(key: str, old_text: str, new_text: str, note: str = "") -> str:
        rev = store.patch(key, old_text, new_text, trailer=note)
        return f"patched {key} at revision {rev}"

    async def remove(key: str, note: str = "") -> str:
        rev = store.delete(key, trailer=note)
        return f"deleted {key} at revision {rev}"

    async def history(key: str, limit: int = 10) -> str:
        revisions = store.history(key, limit=limit)
        if not revisions:
            return f"{key} has no history"
        return "\n".join(
            f"{item.rev}  {item.author}  {item.message.splitlines()[0]}" for item in revisions
        )

    async def diff(key: str, rev_a: str, rev_b: str) -> str:
        return store.diff(key, rev_a, rev_b) or "no difference between those revisions"

    async def restore(key: str, rev: str) -> str:
        new_rev = store.restore(key, rev)
        return f"restored {key} from {rev} as a new revision {new_rev}"

    tools = [
        ToolSpec(
            name=name("list"),
            description=f"List {namespace} keys, optionally under a prefix. Start here.",
            parameters=_parameters(prefix={"type": "string", "description": "Namespace prefix."}),
            handler=list_keys
        ),
        ToolSpec(
            name=name("view"),
            description=f"Read one {namespace} body. Use after `{namespace}:list`.",
            parameters=_parameters(key={"type": "string", "_required": True}),
            handler=view
        ),
        ToolSpec(
            name=name("write"),
            description=(
                f"Write a {namespace} body, replacing it if the key exists. {guidance} "
                "Returns the revision you can restore later."
            ),
            parameters=_parameters(
                key={"type": "string", "_required": True},
                body={"type": "string", "_required": True},
                note={"type": "string", "description": "Why this change was made."}
            ),
            handler=write
        ),
        ToolSpec(
            name=name("patch"),
            description=(
                f"Replace one exact substring in a {namespace} body. Prefer this over "
                "rewriting the whole body."
            ),
            parameters=_parameters(
                key={"type": "string", "_required": True},
                old_text={"type": "string", "_required": True},
                new_text={"type": "string", "_required": True},
                note={"type": "string"}
            ),
            handler=patch
        ),
        ToolSpec(
            name=name("delete"),
            description=f"Delete a {namespace} key. History survives; this is recoverable.",
            parameters=_parameters(
                key={"type": "string", "_required": True},
                note={"type": "string"}
            ),
            handler=remove
        ),
        ToolSpec(
            name=name("history"),
            description=f"Show past revisions of a {namespace} key, newest first.",
            parameters=_parameters(
                key={"type": "string", "_required": True},
                limit={"type": "integer"}
            ),
            handler=history
        ),
        ToolSpec(
            name=name("diff"),
            description=f"Compare two revisions of a {namespace} key.",
            parameters=_parameters(
                key={"type": "string", "_required": True},
                rev_a={"type": "string", "_required": True},
                rev_b={"type": "string", "_required": True}
            ),
            handler=diff
        ),
        ToolSpec(
            name=name("restore"),
            description=(
                f"Bring an old {namespace} body back. This appends a new revision instead of "
                "rewinding, so nothing is lost."
            ),
            parameters=_parameters(
                key={"type": "string", "_required": True},
                rev={"type": "string", "_required": True}
            ),
            handler=restore
        )
    ]
    if index is not None:
        tools.append(
            ToolSpec(
                name=name("search"),
                description=(
                    f"Search {namespace} bodies by text and get matching keys with a snippet. "
                    f"Use this before `{namespace}:list` when you do not know the key."
                ),
                parameters=_parameters(
                    query={"type": "string", "_required": True},
                    limit={"type": "integer"},
                    prefix={"type": "string"}
                ),
                handler=_search_handler(index)
            )
        )
    return tools


def _search_handler(index: KVSearchIndex):
    async def search(query: str, limit: int = 10, prefix: str = "") -> str:
        hits = index.search(query, limit=limit, prefix=prefix)
        if not hits:
            return f"nothing matched {query!r}"
        return "\n".join(f"{hit.key}\n    {hit.snippet.strip()}" for hit in hits)

    return search
