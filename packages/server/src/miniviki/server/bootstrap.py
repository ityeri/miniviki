import os
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

from miniviki.core.agent import AgentLoop, ApprovalGate
from miniviki.core.context import ContextLock, ContextStore, EventLog
from miniviki.core.errors import MinivikiError
from miniviki.core.hooks import HookBus
from miniviki.core.index import KVSearchIndex
from miniviki.core.kv import VersionedKVStore
from miniviki.core.llm import LLMClient
from miniviki.core.tools import Toolset
from miniviki.sandbox import LocalSandboxProvider, SandboxProvider

HOME_ENV_VAR = "MINIVIKI_HOME"
DEFAULT_HOME = ".miniviki"


@dataclass(frozen=True, slots=True)
class HomeLayout:
    """Where the runtime lives. The repo holds code and bundle originals, never this."""

    root: Path

    @property
    def contexts_db(self) -> Path:
        return self.root / "contexts.db"

    @property
    def memory(self) -> Path:
        return self.root / "memory"

    @property
    def skills(self) -> Path:
        return self.root / "skills"

    @property
    def memory_index(self) -> Path:
        return self.root / "indexes" / "memory.db"

    @property
    def skill_index(self) -> Path:
        return self.root / "indexes" / "skills.db"

    @property
    def workspaces(self) -> Path:
        return self.root / "workspaces"

    @property
    def agents(self) -> Path:
        return self.root / "agents"

    @classmethod
    def resolve(cls, root: Path | str | None = None) -> HomeLayout:
        if root is not None:
            return cls(root=Path(root))
        from_environment = os.environ.get(HOME_ENV_VAR)
        if from_environment:
            return cls(root=Path(from_environment))
        return cls(root=Path.home() / DEFAULT_HOME)

    def ensure(self) -> HomeLayout:
        for directory in (self.root, self.workspaces, self.agents, self.root / "indexes"):
            directory.mkdir(parents=True, exist_ok=True)
        return self

    def workspace_for(self, context_id: str) -> Path:
        return self.workspaces / context_id


def load_default_soul() -> str:
    resource = resources.files("miniviki.server").joinpath("bundles/default/soul.md")
    return resource.read_text(encoding="utf-8") if resource.is_file() else ""


def load_agent_soul(layout: HomeLayout, name: str | None) -> str:
    if not name:
        return ""
    path = layout.agents / name / "soul.md"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


@dataclass(slots=True)
class Runtime:
    """Everything a session needs, assembled once and shared."""

    layout: HomeLayout
    log: EventLog
    contexts: ContextStore
    memory: VersionedKVStore
    skills: VersionedKVStore
    memory_index: KVSearchIndex
    skill_index: KVSearchIndex
    llm: LLMClient
    hooks: HookBus
    approvals: ApprovalGate
    lock: ContextLock
    sandbox_provider: SandboxProvider
    exec_requires_approval: bool = False

    @classmethod
    def build(
        cls,
        llm: LLMClient | None = None,
        home: Path | str | None = None,
        hooks: HookBus | None = None,
        sandbox_provider: SandboxProvider | None = None,
        exec_requires_approval: bool = False
    ) -> Runtime:
        if llm is None:
            raise MinivikiError("a runtime needs an LLM client; pass one in")
        layout = HomeLayout.resolve(home).ensure()
        log = EventLog(path=layout.contexts_db)
        memory = VersionedKVStore.open(layout.memory, author="miniviki")
        skills = VersionedKVStore.open(layout.skills, author="miniviki")
        return cls(
            layout=layout,
            log=log,
            contexts=ContextStore(log=log),
            memory=memory,
            skills=skills,
            memory_index=KVSearchIndex(
                store=memory.store, path=layout.memory_index, table="memory"
            ),
            skill_index=KVSearchIndex(
                store=skills.store, path=layout.skill_index, table="skills"
            ),
            llm=llm,
            hooks=hooks or HookBus(),
            approvals=ApprovalGate(),
            lock=ContextLock(),
            sandbox_provider=sandbox_provider or LocalSandboxProvider(),
            exec_requires_approval=exec_requires_approval
        )

    def loop(self, toolset: Toolset, system: str) -> AgentLoop:
        return AgentLoop(
            llm=self.llm,
            log=self.log,
            toolset=toolset,
            hooks=self.hooks,
            approvals=self.approvals,
            lock=self.lock,
            system=system
        )

    def skill_index_lines(self) -> list[str]:
        return [
            f"{key} — {self.skills.read(key).strip().splitlines()[0]}"
            for key in self.skills.keys()  # noqa: SIM118 -- a store, not a dict
            if self.skills.read(key).strip()
        ]

    def aclose(self) -> None:
        self.memory_index.close()
        self.skill_index.close()
        self.log.close()
