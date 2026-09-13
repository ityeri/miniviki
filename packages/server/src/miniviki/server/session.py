import asyncio
from dataclasses import dataclass, field

from miniviki.core.context import ContextKind, ContextRecord, EventKind
from miniviki.core.errors import ContextNotFound
from miniviki.core.prompt import AGENT_LAYER, CONTEXT_LAYER, GLOBAL_LAYER, SoulLayer, assemble
from miniviki.core.tools import (
    Toolset,
    ToolSpec,
    build_exec_tool,
    build_memory_tools,
    build_skill_tools,
    build_spawn_tool,
)
from miniviki.mca import ClientCapability, ClientTool, ContextHandle, ContextInit
from miniviki.sandbox import Sandbox, SandboxSpec

from .bootstrap import Runtime, load_agent_soul, load_default_soul
from .negotiation import Negotiation, negotiate

MAX_SPAWN_DEPTH = 1
CHILD_KINDS = ("subagent", "quick", "fork")
SPAWN_DEPTH_EXCEEDED = (
    "error: this context is already a child. Nesting stops at depth {depth}. "
    "Do the work here instead."
)


@dataclass(slots=True)
class Session:
    """One live context: its toolset, its workspace, and the task currently driving it."""

    record: ContextRecord
    init: ContextInit
    toolset: Toolset
    sandbox: Sandbox
    system: str
    negotiation: Negotiation
    task: asyncio.Task | None = None

    @property
    def id(self) -> str:
        return self.record.id

    @property
    def capabilities(self) -> ClientCapability:
        return self.init.capabilities

    def handle(self) -> ContextHandle:
        return ContextHandle(
            id=self.record.id,
            kind=str(self.record.kind),
            toolset_version=self.record.toolset_version,
            initial_context_digest=self.record.initial_context_digest,
            label=self.record.label
        )


@dataclass(slots=True)
class SessionRegistry:
    """Creates contexts and keeps their live state. The context id is the only handle."""

    runtime: Runtime
    max_spawn_depth: int = MAX_SPAWN_DEPTH
    sessions: dict[str, Session] = field(default_factory=dict)
    depths: dict[str, int] = field(default_factory=dict)

    async def create(self, init: ContextInit, depth: int = 0) -> Session:
        record = self.runtime.contexts.create(
            kind=_kind_of(init.kind),
            parent_id=init.parent_id,
            label=init.label,
            soul_ref=init.soul_ref,
            owner_id="server"
        )
        sandbox = await self.runtime.sandbox_provider.provision(
            SandboxSpec(root_dir=str(self.runtime.layout.workspace_for(record.id)))
        )
        negotiation = negotiate(
            self._base_specs(sandbox, record.id, depth),
            init.tools,
            init.capabilities
        )
        initial = self._assemble(init, negotiation)
        record = self.runtime.contexts.update(
            record.id,
            toolset_version=negotiation.toolset.version,
            initial_context_digest=initial.digest
        )
        session = Session(
            record=record,
            init=init,
            toolset=negotiation.toolset,
            sandbox=sandbox,
            system=initial.text,
            negotiation=negotiation
        )
        self.sessions[record.id] = session
        self.depths[record.id] = depth
        if negotiation.dropped:
            self._note(session, session.negotiation.summary())
        return session

    def get(self, context_id: str) -> Session:
        session = self.sessions.get(context_id)
        if session is None:
            raise ContextNotFound(context_id)
        return session

    async def update_tools(self, context_id: str, tools: list[ClientTool]) -> Session:
        session = self.get(context_id)
        previous = session.toolset
        session.init = _with_tools(session.init, tools)
        negotiation = negotiate(
            self._base_specs(session.sandbox, session.id, self.depths[session.id]),
            session.init.tools,
            session.capabilities
        )
        session.toolset = negotiation.toolset
        session.negotiation = negotiation
        session.system = self._assemble(session.init, negotiation).text
        session.record = self.runtime.contexts.update(
            session.id,
            toolset_version=negotiation.toolset.version
        )
        difference = previous.diff(negotiation.toolset)
        if not difference.is_empty():
            self._note(
                session,
                difference.render(
                    previous.version,
                    negotiation.toolset.version,
                    previous.client_label,
                    negotiation.toolset.client_label
                )
            )
        return session

    async def run_to_completion(self, session: Session, text: str | None = None):
        loop = self.runtime.loop(session.toolset, session.system)
        return await loop.run(session.id, user_input=text)

    def final_text(self, context_id: str) -> str:
        return "".join(
            str(event.payload.get("content", ""))
            for event in self.runtime.log.read(context_id)
            if event.kind is EventKind.MESSAGE and event.payload.get("role") == "assistant"
        )

    async def drop(self, context_id: str) -> None:
        session = self.sessions.pop(context_id, None)
        self.depths.pop(context_id, None)
        if session is not None:
            await session.sandbox.teardown()

    def _base_specs(self, sandbox: Sandbox, context_id: str, depth: int) -> list[ToolSpec]:
        return [
            build_exec_tool(sandbox, requires_approval=self.runtime.exec_requires_approval),
            *build_memory_tools(self.runtime.memory, self.runtime.memory_index),
            *build_skill_tools(self.runtime.skills, self.runtime.skill_index),
            build_spawn_tool(self._spawner(context_id, depth))
        ]

    def _spawner(self, parent_id: str, depth: int):
        async def spawn(prompt: str, kind: str = "subagent", mode: str = "fresh") -> str:
            if depth >= self.max_spawn_depth:
                return SPAWN_DEPTH_EXCEEDED.format(depth=self.max_spawn_depth)
            child = await self.create(
                ContextInit(
                    kind=kind if kind in CHILD_KINDS else "subagent",
                    parent_id=parent_id,
                    label=prompt[:60]
                ),
                depth=depth + 1
            )
            record = await self.run_to_completion(child, prompt)
            answer = self.final_text(child.id)
            if answer:
                return answer
            return f"the child context ended with status {record.status} and said nothing"

        return spawn

    def _assemble(self, init: ContextInit, negotiation: Negotiation):
        souls = [
            SoulLayer(name=GLOBAL_LAYER, body=load_default_soul()),
            SoulLayer(name=AGENT_LAYER, body=load_agent_soul(self.runtime.layout, init.soul_ref)),
            SoulLayer(name=CONTEXT_LAYER, body="")
        ]
        return assemble(
            souls,
            negotiation.toolset,
            skill_index=self.runtime.skill_index_lines(),
            memory_summary=""
        )

    def _note(self, session: Session, text: str) -> None:
        self.runtime.log.append(
            session.id,
            EventKind.BOUNDARY,
            {"text": f"<context_boundary>{text}</context_boundary>", "boundary": text}
        )


def _kind_of(raw: str) -> ContextKind:
    try:
        return ContextKind(raw)
    except ValueError as error:
        allowed = ", ".join(str(item) for item in ContextKind)
        raise ValueError(f"unknown context kind {raw!r}; expected one of {allowed}") from error


def _with_tools(init: ContextInit, tools: list[ClientTool]) -> ContextInit:
    return ContextInit(
        kind=init.kind,
        parent_id=init.parent_id,
        label=init.label,
        soul_ref=init.soul_ref,
        capabilities=init.capabilities,
        tools=tuple(tools)
    )
