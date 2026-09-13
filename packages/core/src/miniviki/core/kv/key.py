from ..constants import DEFAULT_MAX_KEY_CHARS, NAMESPACE_SEPARATOR
from ..errors import InvalidKey

_ALLOWED_EXTRA = {"_", "-"}
_FORBIDDEN = {".", "/", "\\", "\x00", " ", "\t", "\n", "\r"}


def validate_key(key: str, max_key_chars: int = DEFAULT_MAX_KEY_CHARS) -> str:
    """Reject anything that is not a plain `word:word:word` namespace path.

    A key is a list of tokens, never a path: we refuse separators inside a word
    (`soul.md` is not a key) and we refuse traversal outright, so the filepath
    mapping stays an implementation detail nobody can reach.
    """
    if not key:
        raise InvalidKey("key must not be empty")
    if len(key) > max_key_chars:
        raise InvalidKey(f"key exceeds {max_key_chars} characters")
    if key.startswith(NAMESPACE_SEPARATOR) or key.endswith(NAMESPACE_SEPARATOR):
        raise InvalidKey("key must not start or end with the namespace separator")
    for char in key:
        if char in _FORBIDDEN:
            raise InvalidKey(f"key contains a forbidden character: {char!r}")
    parts = key.split(NAMESPACE_SEPARATOR)
    for part in parts:
        if not part:
            raise InvalidKey("key contains an empty segment")
        for char in part:
            if char.isalnum() or char in _ALLOWED_EXTRA:
                continue
            raise InvalidKey(f"segment {part!r} contains an unsupported character: {char!r}")
    return NAMESPACE_SEPARATOR.join(parts)


def key_parts(key: str) -> tuple[str, ...]:
    return tuple(validate_key(key).split(NAMESPACE_SEPARATOR))


def key_to_relative_path(key: str, suffix: str = ".md") -> str:
    """Internal mapping onto a relative filepath. Never expose this to callers.

    Only the last segment carries the suffix, so one key is one file and git
    diffs stay per-key instead of rewriting a monolith.
    """
    parts = key_parts(key)
    return "/".join([*parts[:-1], f"{parts[-1]}{suffix}"])


def key_parent(prefix: str) -> tuple[str, ...]:
    return key_parts(prefix) if prefix else ()


def is_under(key: str, prefix: str) -> bool:
    if not prefix:
        return True
    parts = key_parts(key)
    head = key_parent(prefix)
    return parts[: len(head)] == head
