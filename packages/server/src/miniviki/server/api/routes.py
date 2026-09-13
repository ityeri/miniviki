import asyncio
from collections.abc import AsyncIterator

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import StreamingResponse
from miniviki.core.agent import Decision
from miniviki.core.context import EventKind
from miniviki.core.errors import ApprovalRequired, ContextNotFound
from miniviki.mca import ClientCapability, ClientTool, ContextInit

from ..orchestration.runner import RunDriver
from ..session import Session, SessionRegistry
from .sse import format_sse, to_wire

POLL_INTERVAL = 0.05
READ_BATCH = 200
OPTIONAL_BODY = Body(None)   # B008: FastAPI reads the default object itself


def build_router(registry: SessionRegistry, driver: RunDriver) -> APIRouter:
    router = APIRouter()

    @router.post("/contexts")
    async def create_context(body: dict | None = OPTIONAL_BODY) -> dict:
        try:
            session = await registry.create(_init_of(body or {}))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return handle_payload(session)

    @router.get("/contexts/{context_id}")
    async def context_state(context_id: str) -> dict:
        return handle_payload(_require(registry, context_id))

    @router.post("/contexts/{context_id}/input")
    async def submit(context_id: str, body: dict | None = OPTIONAL_BODY) -> dict:
        session = _require(registry, context_id)
        text = str((body or {}).get("text", ""))
        if not text:
            raise HTTPException(status_code=400, detail="text is required")
        run_id = driver.start(session, text)
        if not run_id:
            raise HTTPException(status_code=409, detail="a run is already active on this context")
        return {"run_id": run_id}

    @router.get("/contexts/{context_id}/events")
    async def events(context_id: str, from_seq: int = 0) -> StreamingResponse:
        session = _require(registry, context_id)
        return StreamingResponse(
            _stream(registry, driver, session, from_seq),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
        )

    @router.post("/contexts/{context_id}/interrupt")
    async def interrupt(context_id: str) -> dict:
        return {"ok": await driver.interrupt(_require(registry, context_id))}

    @router.post("/contexts/{context_id}/approvals")
    async def resolve_approval(context_id: str, body: dict | None = OPTIONAL_BODY) -> dict:
        session = _require(registry, context_id)
        payload = body or {}
        call_id = str(payload.get("call_id", ""))
        try:
            decision = Decision(str(payload.get("decision", "")))
        except ValueError as error:
            raise HTTPException(
                status_code=400,
                detail=f"decision must be one of {', '.join(str(item) for item in Decision)}"
            ) from error
        try:
            registry.runtime.approvals.resolve(call_id, decision)
        except ApprovalRequired as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return {"ok": True, "decision": str(decision), "run_id": driver.start(session)}

    @router.post("/contexts/{context_id}/tools")
    async def update_tools(context_id: str, body: dict | None = OPTIONAL_BODY) -> dict:
        tools = [
            ClientTool.from_json(raw) for raw in (body or {}).get("tools") or []
        ]
        session = await registry.update_tools(context_id, tools)
        return handle_payload(session)

    return router


def handle_payload(session: Session) -> dict:
    """The wire handle. Kept next to ContextHandle.from_json, which reads it back."""
    handle = session.handle()
    return {
        "id": handle.id,
        "kind": handle.kind,
        "toolset_version": handle.toolset_version,
        "initial_context_digest": handle.initial_context_digest,
        "label": handle.label
    }


def _init_of(body: dict) -> ContextInit:
    return ContextInit(
        kind=str(body.get("kind", "main")),
        parent_id=body.get("parent_id"),
        label=str(body.get("label", "")),
        soul_ref=body.get("soul_ref"),
        capabilities=ClientCapability.from_json(body.get("capabilities") or {}),
        tools=tuple(ClientTool.from_json(raw) for raw in body.get("tools") or [])
    )


def _require(registry: SessionRegistry, context_id: str) -> Session:
    try:
        return registry.get(context_id)
    except ContextNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


async def _stream(
    registry: SessionRegistry,
    driver: RunDriver,
    session: Session,
    from_seq: int
) -> AsyncIterator[str]:
    cursor = from_seq
    while True:
        events = registry.runtime.log.read(session.id, from_seq=cursor, limit=READ_BATCH)
        if not events:
            if not driver.running(session):
                return
            await asyncio.sleep(POLL_INTERVAL)
            continue
        for event in events:
            cursor = event.seq + 1
            wire = to_wire(event)
            if wire is not None:
                yield format_sse(wire)
            if event.kind is EventKind.RUN_END:
                return
