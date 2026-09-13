from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .result import ExecResult


@dataclass(frozen=True, slots=True)
class SandboxSpec:
    """Declarative description of the executor we want.

    Says nothing about a host directory on purpose. The local backend maps
    root_dir onto a temp directory, a container backend onto an image, a pod
    backend onto a pod spec -- and nothing downstream may depend on that
    mapping.
    """

    root_dir: str | None = None
    cpu_limit: float | None = None
    memory_limit_mb: int | None = None
    read_only_root: bool = False
    network: bool = True
    env: Mapping[str, str] = field(default_factory=dict)


@runtime_checkable
class Sandbox(Protocol):
    """A provisioned executor. Ephemeral by default; persistence is a volume concern."""

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult: ...
    def stream(self, command: str, timeout: float | None = None) -> AsyncIterator[str]: ...
    async def teardown(self) -> None: ...


@runtime_checkable
class SandboxProvider(Protocol):
    """Declarative spec in, provisioned executor out."""

    async def provision(self, spec: SandboxSpec) -> Sandbox: ...
