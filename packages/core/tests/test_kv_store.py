import pytest
from miniviki.core import InvalidKey, KVError, KVKeyNotFound, KVLimitExceeded
from miniviki.core.kv import KVStore


def build(tmp_path, **kwargs) -> KVStore:
    return KVStore(root=tmp_path / "store", **kwargs)


def test_body_round_trips(tmp_path):
    store = build(tmp_path)
    store.set("memory:user:ide", "PyCharm")
    assert store.get("memory:user:ide") == "PyCharm"


def test_missing_key_raises(tmp_path):
    with pytest.raises(KVKeyNotFound):
        build(tmp_path).get("memory:nope")


def test_keys_are_filtered_by_prefix(tmp_path):
    store = build(tmp_path)
    store.set("memory:user:ide", "a")
    store.set("memory:agent:name", "b")
    store.set("skill:ydpy", "c")
    assert store.keys("memory:user") == ["memory:user:ide"]
    assert store.keys("memory") == ["memory:agent:name", "memory:user:ide"]
    assert store.keys() == ["memory:agent:name", "memory:user:ide", "skill:ydpy"]


def test_patch_replaces_the_first_occurrence(tmp_path):
    store = build(tmp_path)
    store.set("skill:ydpy", "line one\nline two\n")
    store.patch("skill:ydpy", "line two", "line 2")
    assert store.get("skill:ydpy") == "line one\nline 2\n"


def test_patch_without_a_target_is_an_error(tmp_path):
    store = build(tmp_path)
    store.set("skill:ydpy", "body")
    with pytest.raises(KVError):
        store.patch("skill:ydpy", "absent", "x")


def test_delete_removes_the_key(tmp_path):
    store = build(tmp_path)
    store.set("memory:tmp", "x")
    store.delete("memory:tmp")
    assert not store.exists("memory:tmp")
    with pytest.raises(KVKeyNotFound):
        store.delete("memory:tmp")


def test_body_cap_is_enforced(tmp_path):
    store = build(tmp_path, max_body_chars=8)
    with pytest.raises(KVLimitExceeded):
        store.set("memory:big", "x" * 9)


def test_key_cap_is_enforced(tmp_path):
    store = build(tmp_path, max_keys=1)
    store.set("memory:one", "x")
    with pytest.raises(KVLimitExceeded):
        store.set("memory:two", "y")


def test_invalid_key_never_reaches_the_filesystem(tmp_path):
    store = build(tmp_path)
    with pytest.raises(InvalidKey):
        store.set("memory:..:escape", "x")
    assert not (tmp_path / "escape.md").exists()
