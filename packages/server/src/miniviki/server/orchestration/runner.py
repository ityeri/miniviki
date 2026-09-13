import asyncio
import secrets

from miniviki.core.context import EventKind

from ..session import Session, SessionRegistry


class RunDriver:
    """Starts runs, parks them when a tool needs a human, and records how they ended.

    Interruption is a cancel plus a closing event, never a silent drop: the log
    always says what happened, so a client that reconnects sees the truth.
    """

    def __init__(self, registry: SessionRegistry) -> None:
        self.registry = registry

    def running(self, session: Session) -> bool:
        return session.task is not None and not session.task.done()

    def start(self, session: Session, text: str | None = None) -> str:
        if self.running(session):
            return ""
        run_id = f"run_{secrets.token_hex(4)}"
        session.task = asyncio.create_task(self._drive(session, run_id, text))
        return run_id

    async def _drive(self, session: Session, run_id: str, text: str | None) -> None:
        try:
            record = await self.registry.run_to_completion(session, text)
            payload = {**record.to_json(), "run_id": run_id}
        except asyncio.CancelledError:
            payload = {
                "run_id": run_id,
                "status": "interrupted",
                "stop_reason": "the client interrupted this run"
            }
        self.registry.runtime.log.append(session.id, EventKind.RUN_END, payload)

    async def interrupt(self, session: Session) -> bool:
        if not self.running(session):
            return False
        session.task.cancel()
        await self.wait(session)
        return True

    async def wait(self, session: Session) -> None:
        task = session.task
        if task is None:
            return
        try:
            await task
        except asyncio.CancelledError:
            return
