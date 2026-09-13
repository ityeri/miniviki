
from miniviki.core.agent import AgentLoop, Decision, RunStatus
from miniviki.core.context import ContextLock, EventKind, EventLog
from miniviki.core.hooks import BEFORE_TOOL, RUN_END, HookBus, HookPermission
from miniviki.core.llm import ScriptedClient, call, reply
from miniviki.core.tools import Toolset, ToolSpec


def tool(name: str, output: str = "ok", requires_approval: bool = False, **kwargs) -> ToolSpec:
    async def handler(**_arguments: object) -> str:
        return output

    return ToolSpec(
        name=name,
        description=f"{name} does a thing",
        handler=handler,
        requires_approval=requires_approval,
        **kwargs
    )


def build(tmp_path, script, specs, **kwargs) -> tuple[AgentLoop, EventLog, str]:
    log = EventLog(path=tmp_path / "ctx.db")
    log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "start"})
    loop = AgentLoop(
        llm=ScriptedClient(script=script),
        log=log,
        toolset=Toolset.from_specs(specs),
        **kwargs
    )
    return loop, log, "ctx_a"


def first_event(log: EventLog, context_id: str, kind: EventKind):
    return next(event for event in log.read(context_id) if event.kind is kind)


def kinds(log: EventLog, context_id: str) -> list[str]:
    return [str(event.kind) for event in log.read(context_id)]


async def test_plain_reply_finishes_the_run(tmp_path):
    loop, log, ctx = build(tmp_path, [reply("done", prompt_tokens=10, completion_tokens=3)], [])
    record = await loop.run(ctx, user_input="hello")
    assert record.status is RunStatus.DONE
    assert record.steps == 1
    assert record.prompt_tokens == 10
    assert kinds(log, ctx) == ["message", "message", "message"]


async def test_tool_call_then_reply(tmp_path):
    loop, log, ctx = build(
        tmp_path,
        [call("exec", {"command": "ls"}, call_id="c1"), reply("all done")],
        [tool("exec", output="file_a\nfile_b")]
    )
    record = await loop.run(ctx, user_input="list files")
    assert record.status is RunStatus.DONE
    # steps counts loop iterations: think, dispatch, think again
    assert record.steps == 3
    assert kinds(log, ctx) == ["message", "message", "tool_call", "tool_result", "message"]
    result = first_event(log, ctx, EventKind.TOOL_RESULT)
    assert result.payload["content"] == "file_a\nfile_b"
    assert result.payload["call_id"] == "c1"


async def test_the_frozen_toolset_is_what_the_model_sees(tmp_path):
    loop, _log, ctx = build(tmp_path, [reply("ok")], [tool("exec"), tool("memory_view")])
    await loop.run(ctx, user_input="hi")
    assert loop.llm.tools_seen[0] == ("exec", "memory_view")


async def test_unknown_tool_tells_the_model_what_to_do_instead(tmp_path):
    script = [call("client_shell", {}, call_id="c1"), reply("ok")]
    loop, log, ctx = build(tmp_path, script, [tool("exec")])
    await loop.run(ctx, user_input="hi")
    result = first_event(log, ctx, EventKind.TOOL_RESULT)
    assert "no tool named 'client_shell'" in result.payload["content"]
    assert "pick one that exists" in result.payload["content"]


async def test_a_failing_tool_becomes_text_not_a_crash(tmp_path):
    async def explode(**_arguments: object) -> str:
        raise RuntimeError("disk on fire")

    specs = [ToolSpec(name="exec", description="d", handler=explode)]
    loop, log, ctx = build(tmp_path, [call("exec", {}, call_id="c1"), reply("ok")], specs)
    record = await loop.run(ctx, user_input="hi")
    assert record.status is RunStatus.DONE
    result = first_event(log, ctx, EventKind.TOOL_RESULT)
    assert "disk on fire" in result.payload["content"]


async def test_bad_arguments_are_reported_with_guidance(tmp_path):
    async def needs_command(command: str) -> str:
        return command

    specs = [ToolSpec(name="exec", description="d", handler=needs_command)]
    loop, log, ctx = build(tmp_path, [call("exec", {}, call_id="c1"), reply("ok")], specs)
    await loop.run(ctx, user_input="hi")
    result = first_event(log, ctx, EventKind.TOOL_RESULT)
    assert "bad arguments for exec" in result.payload["content"]
    assert "call again" in result.payload["content"]


async def test_result_budget_truncates_what_enters_the_log(tmp_path):
    loop, log, ctx = build(
        tmp_path,
        [call("exec", {}, call_id="c1"), reply("ok")],
        [tool("exec", output="x" * 500, max_result_chars=20)]
    )
    await loop.run(ctx, user_input="hi")
    result = first_event(log, ctx, EventKind.TOOL_RESULT)
    assert result.payload["content"].startswith("x" * 20)
    assert "truncated: 480" in result.payload["content"]


async def test_approval_tool_parks_the_run(tmp_path):
    specs = [tool("exec", requires_approval=True)]
    script = [call("exec", {"command": "rm -rf /"}, call_id="c1"), reply("ok")]
    loop, log, ctx = build(tmp_path, script, specs)
    record = await loop.run(ctx, user_input="clean up")
    assert record.status is RunStatus.WAITING_APPROVAL
    assert kinds(log, ctx) == ["message", "message", "tool_call", "approval"]
    assert loop.approvals.pending()[0].tool == "exec"


async def test_approval_event_carries_a_readable_request(tmp_path):
    specs = [tool("exec", requires_approval=True)]
    loop, log, ctx = build(tmp_path, [call("exec", {}, call_id="c1")], specs)
    await loop.run(ctx, user_input="go")
    event = first_event(log, ctx, EventKind.APPROVAL)
    assert "<approval_request tool=\"exec\" call=\"c1\">" in event.payload["text"]
    assert event.payload["decision"] == "pending"


async def test_run_resumes_after_the_approval_is_granted(tmp_path):
    specs = [tool("exec", output="cleaned", requires_approval=True)]
    loop, log, ctx = build(
        tmp_path,
        [call("exec", {}, call_id="c1"), reply("all clean")],
        specs
    )
    parked = await loop.run(ctx, user_input="clean up")
    assert parked.status is RunStatus.WAITING_APPROVAL
    loop.approvals.resolve("c1", Decision.APPROVED)
    resumed = await loop.run(ctx)
    assert resumed.status is RunStatus.DONE
    results = [e.payload["content"] for e in log.read(ctx) if e.kind is EventKind.TOOL_RESULT]
    assert results == ["cleaned"]


async def test_denied_approval_never_runs_the_tool(tmp_path):
    specs = [tool("exec", output="SHOULD NOT APPEAR", requires_approval=True)]
    loop, log, ctx = build(tmp_path, [call("exec", {}, call_id="c1"), reply("understood")], specs)
    await loop.run(ctx, user_input="go")
    loop.approvals.resolve("c1", Decision.DENIED)
    record = await loop.run(ctx)
    assert record.status is RunStatus.DONE
    results = [e.payload["content"] for e in log.read(ctx) if e.kind is EventKind.TOOL_RESULT]
    assert results == ["denied by the user"]


async def test_an_unanswered_approval_stays_parked(tmp_path):
    specs = [tool("exec", requires_approval=True)]
    loop, log, ctx = build(tmp_path, [call("exec", {}, call_id="c1")], specs)
    await loop.run(ctx, user_input="go")
    second = await loop.run(ctx)
    assert second.status is RunStatus.WAITING_APPROVAL
    assert [e.payload["content"] for e in log.read(ctx) if e.kind is EventKind.TOOL_RESULT] == []


async def test_a_blocking_hook_stops_the_tool(tmp_path):
    hooks = HookBus()

    def guard(context) -> None:
        context.block("vibes are off")

    hooks.subscribe(BEFORE_TOOL, guard, permission=HookPermission.BLOCK)
    specs = [tool("exec", output="SHOULD NOT APPEAR")]
    script = [call("exec", {}, call_id="c1"), reply("ok")]
    loop, log, ctx = build(tmp_path, script, specs, hooks=hooks)
    await loop.run(ctx, user_input="hi")
    results = [e.payload["content"] for e in log.read(ctx) if e.kind is EventKind.TOOL_RESULT]
    assert results == ["blocked: vibes are off"]


async def test_run_end_hook_fires_with_the_record(tmp_path):
    seen: list[object] = []
    hooks = HookBus()
    hooks.subscribe(RUN_END, lambda context: seen.append(context.payload["run"]))
    loop, _log, ctx = build(tmp_path, [reply("ok")], [], hooks=hooks)
    record = await loop.run(ctx, user_input="hi")
    assert seen[0] is record


async def test_step_limit_stops_a_looping_agent(tmp_path):
    script = [call("exec", {}, call_id=f"c{index}") for index in range(10)]
    loop, _log, ctx = build(tmp_path, script, [tool("exec")], max_steps=3)
    record = await loop.run(ctx, user_input="loop forever")
    assert record.steps == 3
    assert record.stop_reason == "step limit reached"


async def test_token_usage_accumulates_across_steps(tmp_path):
    script = [
        call("exec", {}, call_id="c1"),
        reply("done", prompt_tokens=100, completion_tokens=20)
    ]
    loop, _log, ctx = build(tmp_path, script, [tool("exec")], )
    record = await loop.run(ctx, user_input="hi")
    assert record.prompt_tokens == 100
    assert record.completion_tokens == 20


async def test_a_second_writer_is_refused_while_a_run_holds_the_context(tmp_path):
    loop, _log, ctx = build(tmp_path, [reply("ok")], [])
    other = ContextLock()
    other.acquire(ctx, holder="ramyon")
    loop.lock = other
    record = await loop.run(ctx, user_input="hi")
    assert record.status is RunStatus.INTERRUPTED
    assert "already held" in record.stop_reason


async def test_resume_does_not_call_the_model_again_for_a_resolved_call(tmp_path):
    specs = [tool("exec", output="ran")]
    loop, _log, ctx = build(
        tmp_path,
        [call("exec", {}, call_id="c1"), reply("done")],
        specs
    )
    await loop.run(ctx, user_input="hi")
    assert len(loop.llm.seen) == 2
    await loop.run(ctx)
    assert len(loop.llm.seen) == 3
