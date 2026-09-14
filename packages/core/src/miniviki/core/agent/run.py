from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self


class RunStatus(StrEnum):
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_CLIENT = "waiting_client"
    DONE = "done"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True, slots=True)
class RunRecord:
    id: str
    context_id: str
    status: RunStatus
    steps: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    stop_reason: str = ""
    started_at: float = 0.0
    ended_at: float = 0.0

    @property
    def cache_hit_ratio(self) -> float:
        if self.prompt_tokens <= 0:
            return 0.0
        return self.cached_tokens / self.prompt_tokens

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "context_id": self.context_id,
            "status": str(self.status),
            "steps": self.steps,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "stop_reason": self.stop_reason,
            "started_at": self.started_at,
            "ended_at": self.ended_at
        }

    @staticmethod
    def from_json(raw_data: dict[str, Any]) -> Self:
        return RunRecord(
            id=str(raw_data["id"]),
            context_id=str(raw_data["context_id"]),
            status=RunStatus(str(raw_data["status"])),
            steps=int(raw_data.get("steps", 0)),
            prompt_tokens=int(raw_data.get("prompt_tokens", 0)),
            completion_tokens=int(raw_data.get("completion_tokens", 0)),
            cached_tokens=int(raw_data.get("cached_tokens", 0)),
            stop_reason=str(raw_data.get("stop_reason", "")),
            started_at=float(raw_data.get("started_at", 0.0)),
            ended_at=float(raw_data.get("ended_at", 0.0))
        )
