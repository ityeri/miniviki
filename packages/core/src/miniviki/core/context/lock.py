import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from ..errors import ContextLocked


@dataclass(slots=True)
class ContextLock:
    """One writer per context; readers are unrestricted.

    Two surfaces pointing at the same context is the whole point of the design,
    so the lock lives here rather than at the transport. Writes queue or fail;
    reads never block.
    """

    holders: dict[str, str] = field(default_factory=dict)
    guard: threading.Lock = field(default_factory=threading.Lock)

    def acquire(self, context_id: str, holder: str = "run") -> None:
        with self.guard:
            current = self.holders.get(context_id)
            if current is not None:
                raise ContextLocked(f"{context_id} is already held by {current!r}")
            self.holders[context_id] = holder

    def release(self, context_id: str) -> None:
        with self.guard:
            self.holders.pop(context_id, None)

    def holder(self, context_id: str) -> str | None:
        with self.guard:
            return self.holders.get(context_id)

    @contextmanager
    def hold(self, context_id: str, holder: str = "run") -> Iterator[None]:
        self.acquire(context_id, holder)
        try:
            yield
        finally:
            self.release(context_id)
