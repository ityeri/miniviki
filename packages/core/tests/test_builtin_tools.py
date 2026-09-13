import pytest
from miniviki.core import KVKeyNotFound, KVLimitExceeded
from miniviki.core.index import KVSearchIndex
from miniviki.core.kv import KVStore, VersionedKVStore
from miniviki.core.tools import (
    ToolRegistry,
    ToolSpec,
    build_exec_tool,
    build_memory_tools,
    build_skill_tools,
    build_spawn_tool,
)
from miniviki.sandbox import LocalSandboxProvider, SandboxSpec


@pytest.fixture
def memory_tools(tmp_path) -> dict[str, ToolSpec]:
    store = VersionedKVStore.open(tmp_path / "memory", author="ityeri")
    index = KVSearchIndex(store=store.store, path=tmp_path / "indexes.db")
    return {spec.name: spec for spec in build_memory_tools(store, index)}


async def test_exec_tool_runs_in_the_sandbox(tmp_path):
    sandbox = await LocalSandboxProvider().provision(SandboxSpec(root_dir=str(tmp_path)))
    spec = build_exec_tool(sandbox)
    output = await spec.handler(command="echo hi there")
    assert "exit_code: 0" in output
    assert "hi there" in output


async def test_exec_tool_reports_failures_without_raising(tmp_path):
    sandbox = await LocalSandboxProvider().provision(SandboxSpec(root_dir=str(tmp_path)))
    output = await build_exec_tool(sandbox).handler(command="exit 4")
    assert "exit_code: 4" in output


async def test_exec_tool_honours_a_timeout(tmp_path):
    sandbox = await LocalSandboxProvider().provision(SandboxSpec(root_dir=str(tmp_path)))
    output = await build_exec_tool(sandbox).handler(command="sleep 5", timeout=0.2)
    assert "timed_out: true" in output


def test_all_tool_names_live_in_their_own_namespace(memory_tools):
    assert set(memory_tools) == {
        "memory_list",
        "memory_view",
        "memory_write",
        "memory_patch",
        "memory_delete",
        "memory_history",
        "memory_diff",
        "memory_restore",
        "memory_search"
    }


def test_memory_tools_register_without_stepping_on_each_other(memory_tools):
    registry = ToolRegistry()
    for spec in memory_tools.values():
        registry.register(spec)
    assert len(registry.names()) == 9


async def test_write_then_view_round_trip(memory_tools):
    written = await memory_tools["memory_write"].handler(key="memory:user:ide", body="PyCharm")
    assert "revision" in written
    assert await memory_tools["memory_view"].handler(key="memory:user:ide") == "PyCharm"


async def test_list_only_returns_the_index(memory_tools):
    await memory_tools["memory_write"].handler(key="memory:user:ide", body="PyCharm")
    await memory_tools["memory_write"].handler(key="memory:agent:name", body="miniviki")
    listed = await memory_tools["memory_list"].handler()
    assert "memory:user:ide" in listed
    assert "PyCharm" not in listed


async def test_list_on_an_empty_store_says_so(memory_tools):
    assert await memory_tools["memory_list"].handler() == "the store is empty"


async def test_patch_edits_in_place(memory_tools):
    await memory_tools["memory_write"].handler(key="skill:ydpy", body="one\ntwo\n")
    await memory_tools["memory_patch"].handler(key="skill:ydpy", old_text="two", new_text="2")
    assert await memory_tools["memory_view"].handler(key="skill:ydpy") == "one\n2\n"


async def test_history_lists_revisions_newest_first(memory_tools):
    await memory_tools["memory_write"].handler(key="memory:user:ide", body="PyCharm")
    await memory_tools["memory_write"].handler(key="memory:user:ide", body="Neovim")
    listed = await memory_tools["memory_history"].handler(key="memory:user:ide")
    lines = listed.splitlines()
    assert len(lines) == 2
    assert "edit: kv key memory:user:ide" in lines[0]
    assert "add: kv key memory:user:ide" in lines[1]


async def test_diff_shows_the_change(memory_tools):
    first = await memory_tools["memory_write"].handler(key="memory:x", body="PyCharm\n")
    second = await memory_tools["memory_write"].handler(key="memory:x", body="Neovim\n")
    rev_a = first.rsplit(" ", 1)[-1]
    rev_b = second.rsplit(" ", 1)[-1]
    diff = await memory_tools["memory_diff"].handler(key="memory:x", rev_a=rev_a, rev_b=rev_b)
    assert "-PyCharm" in diff
    assert "+Neovim" in diff


async def test_restore_brings_the_old_body_back_without_rewinding(memory_tools):
    first = await memory_tools["memory_write"].handler(key="memory:x", body="PyCharm")
    await memory_tools["memory_write"].handler(key="memory:x", body="Neovim")
    rev = first.rsplit(" ", 1)[-1]
    await memory_tools["memory_restore"].handler(key="memory:x", rev=rev)
    assert await memory_tools["memory_view"].handler(key="memory:x") == "PyCharm"
    assert len((await memory_tools["memory_history"].handler(key="memory:x")).splitlines()) == 3


async def test_delete_is_recoverable(memory_tools):
    await memory_tools["memory_write"].handler(key="memory:tmp", body="x")
    await memory_tools["memory_delete"].handler(key="memory:tmp")
    assert await memory_tools["memory_list"].handler() == "the store is empty"
    assert "memory:tmp" in await memory_tools["memory_history"].handler(key="memory:tmp")


async def test_search_finds_a_body_and_returns_a_snippet(memory_tools):
    await memory_tools["memory_write"].handler(
        key="memory:user:ide",
        body="the user prefers PyCharm"
    )
    await memory_tools["memory_write"].handler(key="memory:user:os", body="the user runs NixOS")
    hits = await memory_tools["memory_search"].handler(query="PyCharm")
    assert "memory:user:ide" in hits
    assert "memory:user:os" not in hits


async def test_search_reports_a_miss_honestly(memory_tools):
    assert "nothing matched" in await memory_tools["memory_search"].handler(query="unicorn")


async def test_search_respects_a_prefix(memory_tools):
    await memory_tools["memory_write"].handler(key="memory:user:ide", body="PyCharm")
    await memory_tools["memory_write"].handler(key="skill:ide", body="PyCharm tips")
    hits = await memory_tools["memory_search"].handler(query="PyCharm", prefix="skill")
    assert "skill:ide" in hits
    assert "memory:user:ide" not in hits


async def test_body_cap_is_enforced_through_the_tools(tmp_path):
    store = VersionedKVStore.open(tmp_path / "small", max_body_chars=8, max_keys=1)
    tools = {spec.name: spec for spec in build_memory_tools(store)}
    await tools["memory_write"].handler(key="memory:one", body="12345678")
    with pytest.raises(KVLimitExceeded):
        await tools["memory_write"].handler(key="memory:one", body="x" * 9)


async def test_key_cap_is_enforced_through_the_tools(tmp_path):
    store = VersionedKVStore.open(tmp_path / "small", max_body_chars=8, max_keys=1)
    tools = {spec.name: spec for spec in build_memory_tools(store)}
    await tools["memory_write"].handler(key="memory:one", body="ok")
    with pytest.raises(KVLimitExceeded):
        await tools["memory_write"].handler(key="memory:two", body="ok")


def test_skill_tools_share_the_factory_but_not_the_namespace(tmp_path):
    store = VersionedKVStore.open(tmp_path / "skills")
    names = {spec.name for spec in build_skill_tools(store)}
    assert "skill_write" in names
    assert "memory_write" not in names


async def test_missing_key_surfaces_as_an_error(tmp_path):
    store = VersionedKVStore.open(tmp_path / "memory")
    tools = {spec.name: spec for spec in build_memory_tools(store)}
    with pytest.raises(KVKeyNotFound):
        await tools["memory_view"].handler(key="memory:nope")


async def test_spawn_tool_delegates_to_the_spawner():
    seen: list[tuple[str, str, str]] = []

    async def spawner(prompt: str, kind: str, mode: str) -> str:
        seen.append((prompt, kind, mode))
        return "child summary"

    spec = build_spawn_tool(spawner)
    assert await spec.handler(prompt="go read the docs") == "child summary"
    assert seen == [("go read the docs", "subagent", "fresh")]


def test_spawn_tool_describes_itself_as_a_context_saver():
    spec = build_spawn_tool(lambda *_: None)
    assert "separate context" in spec.description
    assert "only its final answer" in spec.description


def test_kv_store_direct_is_still_usable(tmp_path):
    store = KVStore(root=tmp_path / "raw")
    store.set("memory:a", "1")
    assert store.get("memory:a") == "1"
