from abc import ABC
from dataclasses import dataclass
from uuid import UUID

from miniviki.llm_interface import Turn


@dataclass(frozen=True, slots=True)
class Context:
    id: UUID
    turns: list[Turn]
    instructions: str | None


class ContextStore(ABC):
    async def spawn(self, ): ...
