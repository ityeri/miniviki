from dataclasses import dataclass
from pathlib import Path

from ..constants import DEFAULT_MAX_BODY_CHARS, DEFAULT_MAX_KEYS, NAMESPACE_SEPARATOR
from ..errors import KVError, KVKeyNotFound, KVLimitExceeded
from .key import is_under, key_to_relative_path, validate_key


@dataclass(frozen=True, slots=True)
class KVEntry:
    key: str
    body: str


@dataclass(slots=True)
class KVStore:
    """A dumb namespaced key/value directory. One file per key, nothing else.

    Knows nothing of versions, locks or policy on purpose -- those live one layer
    up, which is what keeps the backend replaceable.
    """

    root: Path
    suffix: str = ".md"
    max_body_chars: int = DEFAULT_MAX_BODY_CHARS
    max_keys: int = DEFAULT_MAX_KEYS

    def __post_init__(self) -> None:
        self.root = Path(self.root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, key: str) -> Path:
        return self.root / key_to_relative_path(key, self.suffix)

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def get(self, key: str) -> str:
        path = self.path_for(key)
        if not path.is_file():
            raise KVKeyNotFound(key)
        return path.read_text(encoding="utf-8")

    def keys(self, prefix: str = "") -> list[str]:
        found: list[str] = []
        for path in sorted(self.root.rglob(f"*{self.suffix}")):
            if not path.is_file():
                continue
            parts = list(path.relative_to(self.root).parts)
            parts[-1] = parts[-1][: -len(self.suffix)]
            key = NAMESPACE_SEPARATOR.join(parts)
            if is_under(key, prefix):
                found.append(key)
        return found

    def entries(self, prefix: str = "") -> list[KVEntry]:
        return [KVEntry(key=key, body=self.get(key)) for key in self.keys(prefix)]

    def set(self, key: str, body: str) -> KVEntry:
        validated = validate_key(key)
        if len(body) > self.max_body_chars:
            raise KVLimitExceeded(f"body exceeds {self.max_body_chars} characters")
        path = self.path_for(validated)
        if not path.is_file() and len(self.keys()) >= self.max_keys:
            raise KVLimitExceeded(f"store already holds {self.max_keys} keys")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return KVEntry(key=validated, body=body)

    def patch(self, key: str, old_text: str, new_text: str) -> KVEntry:
        body = self.get(key)
        if old_text not in body:
            raise KVError(f"patch target not found in {key!r}")
        return self.set(key, body.replace(old_text, new_text, 1))

    def delete(self, key: str) -> None:
        path = self.path_for(key)
        if not path.is_file():
            raise KVKeyNotFound(key)
        path.unlink()
        parent = path.parent
        while parent != self.root and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
