import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from ..errors import KVError

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
_FIELD = "\x1f"


@dataclass(frozen=True, slots=True)
class Revision:
    rev: str
    author: str
    message: str
    timestamp: str


def store_lock(root: Path) -> threading.Lock:
    """One writer per store. Without it two contexts race git's own index.lock."""
    resolved = str(Path(root).resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(resolved, threading.Lock())


@dataclass(slots=True)
class GitRepo:
    root: Path

    def _run(self, *args: str) -> str:
        proc = subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False
        )
        if proc.returncode != 0:
            raise KVError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
        return proc.stdout

    def init(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        if not (self.root / ".git").exists():
            self._run("init", "-q", "-b", "main")

    def head(self) -> str | None:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False
        )
        return proc.stdout.strip() if proc.returncode == 0 else None

    def dirty(self) -> bool:
        return bool(self._run("status", "--porcelain").strip())

    def commit(self, message: str, author: str = "miniviki") -> str:
        if self.head() is None:
            pass
        elif not self.dirty():
            return self.head() or ""
        self._run("add", "-A")
        self._run(
            "-c", f"user.name={author}",
            "-c", f"user.email={author}@miniviki.local",
            "commit", "-q", "-m", message
        )
        head = self.head()
        if head is None:
            raise KVError("commit produced no HEAD")
        return head

    def log(self, path: str | None = None, limit: int = 50) -> list[Revision]:
        if self.head() is None:
            return []
        args = ["log", f"--format=%h{_FIELD}%an{_FIELD}%at{_FIELD}%s", f"-n{limit}"]
        if path is not None:
            args += ["--", path]
        revisions: list[Revision] = []
        for line in self._run(*args).splitlines():
            if not line.strip():
                continue
            rev, author, timestamp, message = line.split(_FIELD, 3)
            revisions.append(
                Revision(rev=rev, author=author, message=message, timestamp=timestamp)
            )
        return revisions

    def diff(self, path: str, rev_a: str, rev_b: str) -> str:
        return self._run("diff", rev_a, rev_b, "--", path)

    def show(self, rev: str, path: str) -> str:
        proc = subprocess.run(
            ["git", "show", f"{rev}:{path}"],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=False
        )
        if proc.returncode != 0:
            raise KVError(f"{path} does not exist at {rev}")
        return proc.stdout
