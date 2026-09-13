import pytest
from miniviki.core import InvalidKey
from miniviki.core.kv import is_under, key_parent, key_parts, key_to_relative_path, validate_key


def test_namespace_key_is_accepted():
    assert validate_key("memory:user:prefs") == "memory:user:prefs"


def test_single_word_key_is_accepted():
    assert validate_key("skills") == "skills"


def test_parts_are_split_on_the_separator():
    assert key_parts("memory:user:prefs") == ("memory", "user", "prefs")


def test_parent_of_a_nested_key():
    assert key_parent("memory:user") == ("memory", "user")


def test_key_maps_onto_a_relative_path_internally():
    assert key_to_relative_path("memory:user:prefs") == "memory/user/prefs.md"


@pytest.mark.parametrize(
    "key",
    [
        "",
        ":memory",
        "memory:",
        "memory::user",
        "memory:..:user",
        "memory:user/../../etc",
        "/etc/passwd",
        "memory:us er",
        "memory:user.preference",
        "memory:user\x00",
        "soul.md"
    ]
)
def test_invalid_keys_are_rejected(key):
    with pytest.raises(InvalidKey):
        validate_key(key)


def test_overlong_key_is_rejected():
    with pytest.raises(InvalidKey):
        validate_key("a" * 200)


def test_is_under_matches_prefix_boundaries():
    assert is_under("memory:user:prefs", "memory:user")
    assert is_under("memory:user:prefs", "memory")
    assert is_under("memory:user:prefs", "")
    assert not is_under("memory:username", "memory:user")
