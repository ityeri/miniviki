import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .event import ContextEvent, EventKind

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    context_id TEXT NOT NULL,
    seq        INTEGER NOT NULL,
    kind       TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at REAL NOT NULL,
    PRIMARY KEY (context_id, seq)
);
"""


@dataclass(slots=True)
class EventLog:
    """Append-only event store. Nothing in here rewrites or deletes a row.

    A context's message history is a *projection* of this log, never the source
    of truth -- that is what makes mid-run attach and rewind survivable.
    """

    path: Path
    connection: sqlite3.Connection | None = None

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.connection is None:
            self.connection = sqlite3.connect(str(self.path), isolation_level=None)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript(_SCHEMA)

    def last_seq(self, context_id: str) -> int:
        row = self._execute(
            "SELECT COALESCE(MAX(seq), -1) FROM events WHERE context_id = ?",
            (context_id,)
        ).fetchone()
        return int(row[0])

    def append(
        self,
        context_id: str,
        kind: EventKind,
        payload: dict[str, Any],
        created_at: float | None = None
    ) -> ContextEvent:
        seq = self.last_seq(context_id) + 1
        stamp = time.time() if created_at is None else created_at
        self._execute(
            "INSERT INTO events (context_id, seq, kind, payload, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (context_id, seq, str(kind), json.dumps(payload, ensure_ascii=False), stamp)
        )
        return ContextEvent(
            context_id=context_id,
            seq=seq,
            kind=kind,
            payload=payload,
            created_at=stamp
        )

    def read(
        self,
        context_id: str,
        from_seq: int = 0,
        limit: int | None = None
    ) -> list[ContextEvent]:
        sql = (
            "SELECT context_id, seq, kind, payload, created_at FROM events"
            " WHERE context_id = ? AND seq >= ? ORDER BY seq"
        )
        params: list[Any] = [context_id, from_seq]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._execute(sql, tuple(params)).fetchall()
        return [_row_to_event(row) for row in rows]

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None

    def _execute(self, sql: str, params: tuple[Any, ...]) -> sqlite3.Cursor:
        if self.connection is None:
            raise RuntimeError("event log is closed")
        return self.connection.execute(sql, params)


def _row_to_event(row: tuple[Any, ...]) -> ContextEvent:
    return ContextEvent(
        context_id=str(row[0]),
        seq=int(row[1]),
        kind=EventKind(str(row[2])),
        payload=json.loads(row[3]),
        created_at=float(row[4])
    )
