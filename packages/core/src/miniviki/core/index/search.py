import sqlite3
from dataclasses import dataclass
from pathlib import Path

from ..kv import KVStore


def _fts_schema(table: str) -> str:
    return f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING fts5(key, body)"


def _plain_schema(table: str) -> str:
    return f"CREATE TABLE IF NOT EXISTS {table} (key TEXT PRIMARY KEY, body TEXT)"


@dataclass(frozen=True, slots=True)
class SearchHit:
    key: str
    snippet: str


@dataclass(slots=True)
class KVSearchIndex:
    """Recall for keys whose bodies never fit in the prompt.

    The index is derived, never authoritative: it lives outside the store so it
    cannot be mistaken for content and never lands in the store's history.
    """

    store: KVStore
    path: Path
    table: str = "docs"
    connection: sqlite3.Connection | None = None
    fts: bool = True

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.connection is None:
            self.connection = sqlite3.connect(str(self.path), isolation_level=None)
        if not self.table.isidentifier():
            raise ValueError(f"table name must be an identifier, got {self.table!r}")
        try:
            self.connection.executescript(_fts_schema(self.table))
        except sqlite3.OperationalError:
            self.fts = False
            self.connection.executescript(_plain_schema(self.table))

    def reindex(self) -> int:
        connection = self._connection()
        keys = self.store.keys()
        connection.execute(f"DELETE FROM {self.table}")
        for key in keys:
            connection.execute(
                f"INSERT INTO {self.table} (key, body) VALUES (?, ?)",
                (key, self.store.get(key))
            )
        return len(keys)

    def search(self, query: str, limit: int = 10, prefix: str = "") -> list[SearchHit]:
        self.reindex()
        if self.fts:
            return self._fts_search(query, limit, prefix)
        return self._scan_search(query, limit, prefix)

    def _fts_search(self, query: str, limit: int, prefix: str) -> list[SearchHit]:
        connection = self._connection()
        rows = connection.execute(
            f"SELECT key, snippet({self.table}, 1, '', '', ' … ', 12) FROM {self.table}"
            f" WHERE {self.table} MATCH ? ORDER BY rank LIMIT ?",
            (query, limit * 4)
        ).fetchall()
        hits = [
            SearchHit(key=str(row[0]), snippet=str(row[1]))
            for row in rows
            if not prefix or str(row[0]).startswith(prefix)
        ]
        return hits[:limit]

    def _scan_search(self, query: str, limit: int, prefix: str) -> list[SearchHit]:
        needle = query.lower()
        hits: list[SearchHit] = []
        for key in self.store.keys(prefix):
            body = self.store.get(key)
            position = body.lower().find(needle)
            if position < 0:
                continue
            start = max(0, position - 40)
            hits.append(SearchHit(key=key, snippet=body[start : position + len(needle) + 40]))
            if len(hits) >= limit:
                break
        return hits

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _connection(self) -> sqlite3.Connection:
        if self.connection is None:
            raise RuntimeError("search index is closed")
        return self.connection
