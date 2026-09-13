import pytest
from miniviki.core import KVKeyNotFound
from miniviki.core.kv import VersionedKVStore


@pytest.fixture
def store(tmp_path) -> VersionedKVStore:
    return VersionedKVStore.open(tmp_path / "memory", author="ityeri")


def test_first_write_is_an_add_commit(store):
    store.write("memory:user:ide", "PyCharm")
    history = store.history("memory:user:ide")
    assert len(history) == 1
    assert history[0].message == "add: kv key memory:user:ide"
    assert history[0].author == "ityeri"


def test_second_write_is_an_edit_commit(store):
    store.write("memory:user:ide", "PyCharm")
    store.write("memory:user:ide", "Neovim")
    history = store.history("memory:user:ide")
    assert [entry.message.split(":")[0] for entry in history] == ["edit", "add"]
    assert store.read("memory:user:ide") == "Neovim"


def test_restore_writes_the_old_body_forward(store):
    first = store.write("memory:user:ide", "PyCharm")
    store.write("memory:user:ide", "Neovim")
    restored = store.restore("memory:user:ide", first)
    assert store.read("memory:user:ide") == "PyCharm"
    assert restored != first


def test_restore_never_rewinds_history(store):
    first = store.write("memory:user:ide", "PyCharm")
    store.write("memory:user:ide", "Neovim")
    before = len(store.history("memory:user:ide"))
    store.restore("memory:user:ide", first)
    after = store.history("memory:user:ide")
    assert len(after) == before + 1
    assert "restored from" in after[0].message


def test_restore_of_a_revision_without_the_key_is_an_error(store):
    rev = store.write("memory:other", "x")
    with pytest.raises(KVKeyNotFound):
        store.restore("memory:user:ide", rev)


def test_history_survives_deletion(store):
    store.write("memory:user:ide", "PyCharm")
    store.delete("memory:user:ide")
    assert len(store.history("memory:user:ide")) == 2
    assert store.keys() == []


def test_diff_between_two_revisions(store):
    first = store.write("memory:user:ide", "PyCharm\n")
    second = store.write("memory:user:ide", "Neovim\n")
    diff = store.diff("memory:user:ide", first, second)
    assert "-PyCharm" in diff
    assert "+Neovim" in diff


def test_patch_is_recorded_as_an_edit(store):
    store.write("skill:ydpy", "one\ntwo\n")
    store.patch("skill:ydpy", "two", "2")
    history = store.history("skill:ydpy")
    assert history[0].message == "edit: kv key skill:ydpy"
    assert "2" in store.read("skill:ydpy")


def test_keys_are_namespaced_on_disk_not_flat(store):
    store.write("memory:user:prefs:ide", "PyCharm")
    assert (store.store.root / "memory" / "user" / "prefs" / "ide.md").is_file()
