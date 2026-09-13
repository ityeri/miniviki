import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from ..context import ContextLock, EventKind, EventLog, project
from ..errors import ContextLocked, ToolNotFound
from ..hooks import AFTER_LLM, AFTER_TOOL, BEFORE_LLM, BEFORE_TOOL, RUN_END, HookBus
from ..llm import LLMClient
from ..tools import Toolset, ToolSpec
from .approval import ApprovalGate, Decision
from .run import RunRecord, RunStatus

STEP_LIMIT_REASON = "step limit reached"


@dataclass(slots=True)
class AgentLoop:
    """One thread of `think -> call tool -> observe`, driven entirely off the log.

    Resuming is not a special path: on every iteration we look for tool calls that
    have no result yet and finish those first. An approval that was parked
    yesterday therefore resumes today with no extra machinery.
    """

    llm: LLMClient
    log: EventLog
    toolset: Toolset
    hooks: HookBus = field(default_factory=HookBus)
    approvals: ApprovalGate = field(default_factory=ApprovalGate)
    lock: ContextLock = field(default_factory=ContextLock)
    max_steps: int = 24
    holder: str = "core"

    async def run(self, context_id: str, user_input: str | None = None) -> RunRecord:
        try:
            with self.lock.hold(context_id, self.holder):
                if user_input is not None and user_input != "":
                    self.log.append(
                        context_id,
                        EventKind.MESSAGE,
                        {"role": "user", "content": user_input}
                    )
                return await self._drive(context_id)
        except ContextLocked as error:
            return self._finish(
                context_id,
                RunStatus.INTERRUPTED,
                started_at=time.time(),
                stop_reason=str(error)
            )

    async def _drive(self, context_id: str) -> RunRecord:
        started_at = time.time()
        steps = 0
        prompt_tokens = completion_tokens = cached_tokens = 0
        while steps < self.max_steps:
            steps += 1
            outstanding = self._outstanding_calls(context_id)
            if outstanding:
                if await self._dispatch(context_id, outstanding) == "approval":
                    return self._finish(
                        context_id,
                        RunStatus.WAITING_APPROVAL,
                        started_at,
                        steps=steps,
                        stop_reason="a tool is waiting for approval"
                    )
                continue
            completion = await self._think(context_id)
            prompt_tokens += completion.prompt_tokens
            completion_tokens += completion.completion_tokens
            cached_tokens += completion.cached_tokens
            if completion.message.tool_calls:
                self.log.append(
                    context_id,
                    EventKind.TOOL_CALL,
                    {
                        "content": completion.message.content,
                        "calls": [
                            {"id": call.id, "name": call.name, "arguments": call.arguments}
                            for call in completion.message.tool_calls
                        ]
                    }
                )
                continue
            self.log.append(
                context_id,
                EventKind.MESSAGE,
                {"role": "assistant", "content": completion.message.content}
            )
            return self._finish(
                context_id,
                RunStatus.DONE,
                started_at,
                steps=steps,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                stop_reason="assistant finished the turn"
            )
        return self._finish(
            context_id,
            RunStatus.DONE,
            started_at,
            steps=steps,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            stop_reason=STEP_LIMIT_REASON
        )

    async def _think(self, context_id: str):
        messages = project(self.log.read(context_id))
        self.hooks.publish(BEFORE_LLM, {"context_id": context_id, "messages": messages})
        completion = await self.llm.complete(messages, self.toolset.schemas())
        self.hooks.publish(
            AFTER_LLM,
            {"context_id": context_id, "completion": completion}
        )
        return completion

    async def _dispatch(self, context_id: str, calls: list[dict[str, Any]]) -> str:
        for raw in calls:
            call_id = str(raw.get("id", ""))
            name = str(raw.get("name", ""))
            arguments = dict(raw.get("arguments") or {})
            try:
                spec = self.toolset.get(name)
            except ToolNotFound:
                self._result(
                    context_id,
                    call_id,
                    name,
                    f"error: no tool named {name!r} is available in toolset"
                    f" {self.toolset.version}. Check the tool list and pick one that exists."
                )
                continue
            gate = self.hooks.publish(
                BEFORE_TOOL,
                {"context_id": context_id, "tool": name, "arguments": arguments}
            )
            if gate.blocked is not None:
                self._result(context_id, call_id, name, f"blocked: {gate.blocked}")
                continue
            arguments = dict(gate.payload.get("arguments", arguments))
            if spec.requires_approval:
                outcome = self._handle_approval(context_id, spec, call_id, arguments)
                if outcome == "waiting":
                    return "approval"
                if outcome == "denied":
                    continue
            self._result(
                context_id,
                call_id,
                name,
                spec.apply_budget(await self._invoke(spec, arguments)).content
            )
            self.hooks.publish(
                AFTER_TOOL,
                {"context_id": context_id, "tool": name, "arguments": arguments}
            )
        return "continue"

    def _handle_approval(
        self,
        context_id: str,
        spec: ToolSpec,
        call_id: str,
        arguments: dict[str, Any]
    ) -> str:
        decision = self.approvals.check(call_id)
        if decision is Decision.APPROVED:
            return "approved"
        if decision is Decision.DENIED:
            self._result(context_id, call_id, spec.name, "denied by the user")
            return "denied"
        self.approvals.request(call_id, spec.name, arguments)
        self.log.append(
            context_id,
            EventKind.APPROVAL,
            {
                "call_id": call_id,
                "tool": spec.name,
                "arguments": arguments,
                "decision": str(Decision.PENDING),
                "text": (
                    f"<approval_request tool=\"{spec.name}\" call=\"{call_id}\">"
                    "This call is waiting for a human decision. Nothing runs until it is answered."
                    "</approval_request>"
                )
            }
        )
        return "waiting"

    async def _invoke(self, spec: ToolSpec, arguments: dict[str, Any]) -> str:
        if spec.handler is None:
            return f"error: {spec.name} has no handler in this build"
        try:
            return await spec.handler(**arguments)
        except TypeError as error:
            return (
                f"error: bad arguments for {spec.name}: {error}. "
                "Check the tool schema and call again."
            )
        except Exception as error:
            return f"error: {spec.name} failed: {type(error).__name__}: {error}"

    def _outstanding_calls(self, context_id: str) -> list[dict[str, Any]]:
        events = self.log.read(context_id)
        index = -1
        calls: list[dict[str, Any]] = []
        for position, event in enumerate(events):
            if event.kind is EventKind.TOOL_CALL:
                index = position
                calls = list(event.payload.get("calls", []))
        if index < 0:
            return []
        resolved = {
            event.payload.get("call_id")
            for event in events[index + 1 :]
            if event.kind is EventKind.TOOL_RESULT
        }
        return [call for call in calls if call.get("id") not in resolved]

    def _result(self, context_id: str, call_id: str, name: str, content: str) -> None:
        self.log.append(
            context_id,
            EventKind.TOOL_RESULT,
            {"call_id": call_id, "name": name, "content": content}
        )

    def _finish(
        self,
        context_id: str,
        status: RunStatus,
        started_at: float,
        steps: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        stop_reason: str = ""
    ) -> RunRecord:
        record = RunRecord(
            id=f"run_{secrets.token_hex(4)}",
            context_id=context_id,
            status=status,
            steps=steps,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            stop_reason=stop_reason,
            started_at=started_at,
            ended_at=time.time()
        )
        self.hooks.publish(RUN_END, {"context_id": context_id, "run": record})
        return record
