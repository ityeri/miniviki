from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import KVKeyNotFound
from .key import key_to_relative_path, validate_key
from .repo import GitRepo, Revision, store_lock
from .store import KVStore


@dataclass(slots=True)
class VersionedKVStore:
    """KVStore plus write-through history. The agent never sees git.

    Every mutation is exactly one commit and the caller only gets an opaque `rev`
    token back. `restore` writes an old body forward as a *new* commit, so the
    history stays append-only and there is no path that loses data.
    """

    store: KVStore
    repo: GitRepo
    author: str = "miniviki"

    @classmethod
    def open(cls, root: str | Path, author: str = "miniviki", **store_kwargs: Any):
        path = Path(root)
        return cls(store=KVStore(root=path, **store_kwargs), repo=GitRepo(root=path), author=author)

    def __post_init__(self) -> None:
        with store_lock(self.repo.root):
            self.repo.init()

    def _rel(self, key: str) -> str:
        return key_to_relative_path(validate_key(key), self.store.suffix)

    def _commit(self, message: str) -> str:
        with store_lock(self.repo.root):
            return self.repo.commit(message, author=self.author)

    def read(self, key: str) -> str:
        return self.store.get(key)

    def keys(self, prefix: str = "") -> list[str]:
        return self.store.keys(prefix)

    def write(self, key: str, body: str, trailer: str = "", message: str = "") -> str:
        verb = "edit" if self.store.exists(key) else "add"
        message = message or f"{verb}: kv key {key}"
        if trailer:
            message = f"{message}\n\n{trailer}"
        with store_lock(self.repo.root):
            self.store.set(key, body)
            return self.repo.commit(message, author=self.author)

    def patch(self, key: str, old_text: str, new_text: str, trailer: str = "") -> str:
        message = f"edit: kv key {key}"
        if trailer:
            message = f"{message}\n\n{trailer}"
        with store_lock(self.repo.root):
            self.store.patch(key, old_text, new_text)
            return self.repo.commit(message, author=self.author)

    def delete(self, key: str, trailer: str = "") -> str:
        message = f"rm: kv key {key}"
        if trailer:
            message = f"{message}\n\n{trailer}"
        with store_lock(self.repo.root):
            self.store.delete(key)
            return self.repo.commit(message, author=self.author)

    def history(self, key: str, limit: int = 50) -> list[Revision]:
        return self.repo.log(self._rel(key), limit)

    def diff(self, key: str, rev_a: str, rev_b: str) -> str:
        return self.repo.diff(self._rel(key), rev_a, rev_b)

    def restore(self, key: str, rev: str) -> str:
        try:
            body = self.repo.show(rev, self._rel(key))
        except Exception as error:
            raise KVKeyNotFound(f"{key} does not exist at {rev}") from error
        return self.write(key, body, message=f"edit: kv key {key} restored from {rev}")

    def head(self) -> str | None:
        return self.repo.head()
