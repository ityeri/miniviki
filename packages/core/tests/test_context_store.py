import pytest
from miniviki.core import ContextLocked, ContextNotFound
from miniviki.core.context import ContextKind, ContextLock, ContextStore, EventKind, EventLog


@pytest.fixture
def store(tmp_path) -> ContextStore:
    return ContextStore(log=EventLog(path=tmp_path / "contexts.db"))


def test_create_returns_a_labelled_record(store):
    record = store.create(kind=ContextKind.MAIN, label="work")
    assert record.kind is ContextKind.MAIN
    assert record.label == "work"
    assert record.id.startswith("ctx_")


def test_get_of_unknown_context_raises(store):
    with pytest.raises(ContextNotFound):
        store.get("ctx_missing")


def test_every_sub_context_is_the_same_record_shape(store):
    parent = store.create(kind=ContextKind.MAIN)
    for kind in (ContextKind.SIDE, ContextKind.QUICK, ContextKind.FORK, ContextKind.SUBAGENT):
        child = store.create(kind=kind, parent_id=parent.id)
        assert store.get(child.id).kind is kind
    assert len(store.children(parent.id)) == 4


def test_toolset_version_can_be_bumped(store):
    record = store.create(kind=ContextKind.MAIN)
    updated = store.set_toolset_version(record.id, "v7")
    assert updated.toolset_version == "v7"


def test_context_store_reuses_the_log_connection(store):
    parent = store.create(kind=ContextKind.MAIN)
    store.log.append(parent.id, EventKind.MESSAGE, {"content": "hi"})
    assert store.log.read(parent.id)[0].payload["content"] == "hi"


def test_second_writer_on_the_same_context_is_refused():
    lock = ContextLock()
    lock.acquire("ctx_a", holder="ramyon")
    with pytest.raises(ContextLocked):
        lock.acquire("ctx_a", holder="web")
    assert lock.holder("ctx_a") == "ramyon"


def test_release_lets_another_writer_in():
    lock = ContextLock()
    lock.acquire("ctx_a", holder="ramyon")
    lock.release("ctx_a")
    lock.acquire("ctx_a", holder="web")
    assert lock.holder("ctx_a") == "web"


def test_reads_are_not_locked():
    lock = ContextLock()
    lock.acquire("ctx_a", holder="ramyon")
    assert lock.holder("ctx_b") is None


def test_hold_releases_on_exception():
    lock = ContextLock()
    with pytest.raises(ValueError), lock.hold("ctx_a", holder="ramyon"):
        raise ValueError("boom")
    assert lock.holder("ctx_a") is None
