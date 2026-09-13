from dataclasses import dataclass
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return ExecResult(
            exit_code=int(raw_data["exit_code"]),
            stdout=str(raw_data.get("stdout", "")),
            stderr=str(raw_data.get("stderr", "")),
            timed_out=bool(raw_data.get("timed_out", False))
        )
