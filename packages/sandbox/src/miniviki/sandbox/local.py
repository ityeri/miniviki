import asyncio
import logging
import os
import tempfile
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from .base import SandboxSpec
from .result import ExecResult

_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LocalSandbox:
    """Runs commands on this host inside one directory. The v0 backend.

    Cannot enforce cpu_limit, memory_limit_mb, read_only_root or network -- a
    container or pod backend is where those become real. We say so out loud
    rather than pretending to honour them.
    """

    root_dir: str
    env: dict[str, str] = field(default_factory=dict)
    unenforced: tuple[str, ...] = ()

    async def _spawn(self, command: str, stderr_to_stdout: bool) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_shell(
            command,
            cwd=self.root_dir,
            env={**os.environ, **self.env},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT if stderr_to_stdout else asyncio.subprocess.PIPE
        )

    async def exec(self, command: str, timeout: float | None = None) -> ExecResult:
        proc = await self._spawn(command, stderr_to_stdout=False)
        timed_out = False
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            timed_out = True
            proc.kill()
            out, err = await proc.communicate()
            _logger.warning("exec timed out after %ss: %s", timeout, command)
        return ExecResult(
            exit_code=proc.returncode if proc.returncode is not None else -1,
            stdout=out.decode(errors="replace"),
            stderr=err.decode(errors="replace"),
            timed_out=timed_out
        )

    async def stream(self, command: str, timeout: float | None = None) -> AsyncIterator[str]:
        proc = await self._spawn(command, stderr_to_stdout=True)
        stdout = proc.stdout
        if stdout is None:  # pragma: no cover - PIPE was requested, so this cannot happen
            raise RuntimeError("stdout pipe missing")
        try:
            async with asyncio.timeout(timeout):
                async for line in stdout:
                    yield line.decode(errors="replace")
        except TimeoutError:
            _logger.warning("stream timed out after %ss: %s", timeout, command)
        finally:
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

    async def teardown(self) -> None:
        # Nothing durable to release: the workspace is a temp dir by contract,
        # and the caller owns persistence.
        return None


@dataclass(slots=True)
class LocalSandboxProvider:
    async def provision(self, spec: SandboxSpec) -> LocalSandbox:
        root_dir = spec.root_dir or tempfile.mkdtemp(prefix="miniviki-ws-")
        os.makedirs(root_dir, exist_ok=True)
        unenforced = tuple(
            name
            for name, requested in (
                ("cpu_limit", spec.cpu_limit is not None),
                ("memory_limit_mb", spec.memory_limit_mb is not None),
                ("read_only_root", spec.read_only_root),
                ("network", not spec.network)
            )
            if requested
        )
        if unenforced:
            _logger.warning("local backend cannot enforce: %s", ", ".join(unenforced))
        return LocalSandbox(root_dir=root_dir, env=dict(spec.env), unenforced=unenforced)
