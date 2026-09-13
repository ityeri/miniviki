import secrets
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from ..errors import ContextNotFound
from .log import EventLog

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contexts (
    id              TEXT PRIMARY KEY,
    parent_id       TEXT,
    kind            TEXT NOT NULL,
    label           TEXT NOT NULL DEFAULT '',
    soul_ref        TEXT,
    toolset_version TEXT NOT NULL DEFAULT '',
    owner_id        TEXT NOT NULL DEFAULT 'local',
    created_at      REAL NOT NULL,
    initial_context_digest TEXT NOT NULL DEFAULT ''
);
"""


class ContextKind(StrEnum):
    MAIN = "main"
    SIDE = "side"
    QUICK = "quick"
    FORK = "fork"
    SUBAGENT = "subagent"


@dataclass(frozen=True, slots=True)
class ContextRecord:
    id: str
    kind: ContextKind
    parent_id: str | None = None
    label: str = ""
    soul_ref: str | None = None
    toolset_version: str = ""
    owner_id: str = "local"
    created_at: float = 0.0
    initial_context_digest: str = ""

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return ContextRecord(
            id=str(raw_data["id"]),
            kind=ContextKind(str(raw_data["kind"])),
            parent_id=raw_data.get("parent_id"),
            label=str(raw_data.get("label", "")),
            soul_ref=raw_data.get("soul_ref"),
            toolset_version=str(raw_data.get("toolset_version", "")),
            owner_id=str(raw_data.get("owner_id", "local")),
            created_at=float(raw_data.get("created_at") or 0.0),
            initial_context_digest=str(raw_data.get("initial_context_digest", ""))
        )


@dataclass(slots=True)
class ContextStore:
    """Context metadata. Every kind of sub-context is the same record with a different kind."""

    log: EventLog

    def __post_init__(self) -> None:
        if self.log.connection is None:
            raise RuntimeError("context store needs an open event log")
        self.log.connection.executescript(_SCHEMA)
        columns = {
            str(row[1]) for row in self.log.connection.execute('PRAGMA table_info(contexts)')
        }
        if 'initial_context_digest' not in columns:
            self.log.connection.execute(
                "ALTER TABLE contexts ADD COLUMN initial_context_digest"
                " TEXT NOT NULL DEFAULT ''"
            )

    def create(
        self,
        kind: ContextKind = ContextKind.MAIN,
        parent_id: str | None = None,
        label: str = "",
        soul_ref: str | None = None,
        toolset_version: str = "",
        owner_id: str = "local",
        initial_context_digest: str = ""
    ) -> ContextRecord:
        record = ContextRecord(
            id=f"ctx_{secrets.token_hex(6)}",
            kind=kind,
            parent_id=parent_id,
            label=label,
            soul_ref=soul_ref,
            toolset_version=toolset_version,
            owner_id=owner_id,
            created_at=time.time(),
            initial_context_digest=initial_context_digest
        )
        if self.log.connection is None:
            raise RuntimeError("context store is closed")
        self.log.connection.execute(
            "INSERT INTO contexts"
            " (id, parent_id, kind, label, soul_ref, toolset_version, owner_id,"
            " created_at, initial_context_digest)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.parent_id,
                str(record.kind),
                record.label,
                record.soul_ref,
                record.toolset_version,
                record.owner_id,
                record.created_at,
                record.initial_context_digest
            )
        )
        return record

    def get(self, context_id: str) -> ContextRecord:
        if self.log.connection is None:
            raise RuntimeError("context store is closed")
        row = self.log.connection.execute(
            "SELECT id, parent_id, kind, label, soul_ref, toolset_version, owner_id,"
            " created_at, initial_context_digest"
            " FROM contexts WHERE id = ?",
            (context_id,)
        ).fetchone()
        if row is None:
            raise ContextNotFound(context_id)
        return ContextRecord(
            id=str(row[0]),
            kind=ContextKind(str(row[2])),
            parent_id=row[1],
            label=str(row[3]),
            soul_ref=row[4],
            toolset_version=str(row[5]),
            owner_id=str(row[6]),
            created_at=float(row[7]),
            initial_context_digest=str(row[8])
        )

    def children(self, context_id: str) -> list[ContextRecord]:
        if self.log.connection is None:
            raise RuntimeError("context store is closed")
        rows = self.log.connection.execute(
            "SELECT id FROM contexts WHERE parent_id = ? ORDER BY created_at",
            (context_id,)
        ).fetchall()
        return [self.get(str(row[0])) for row in rows]

    def set_toolset_version(self, context_id: str, version: str) -> ContextRecord:
        if self.log.connection is None:
            raise RuntimeError("context store is closed")
        self.log.connection.execute(
            "UPDATE contexts SET toolset_version = ? WHERE id = ?",
            (version, context_id)
        )
        return self.get(context_id)
