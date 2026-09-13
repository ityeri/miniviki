import pytest
from miniviki.core import ContextError
from miniviki.core.context import (
    CompactionPolicy,
    ContextEvent,
    EventKind,
    EventLog,
    compact,
    project,
    should_compact,
)


def make_log(tmp_path) -> EventLog:
    return EventLog(path=tmp_path / "contexts.db")


def test_message_events_project_onto_messages(tmp_path):
    log = make_log(tmp_path)
    log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "hi"})
    log.append("ctx_a", EventKind.MESSAGE, {"role": "assistant", "content": "yo"})
    messages = project(log.read("ctx_a"))
    assert [(message.role, message.content) for message in messages] == [
        ("user", "hi"),
        ("assistant", "yo")
    ]


def test_one_tool_call_event_holds_every_call_of_a_turn(tmp_path):
    log = make_log(tmp_path)
    log.append(
        "ctx_a",
        EventKind.TOOL_CALL,
        {
            "content": "looking around",
            "calls": [
                {"id": "c1", "name": "memory_view", "arguments": {"key": "memory:user"}},
                {"id": "c2", "name": "skill_list", "arguments": {}}
            ]
        }
    )
    messages = project(log.read("ctx_a"))
    assert len(messages) == 1
    assert messages[0].role == "assistant"
    assert [call.name for call in messages[0].tool_calls] == ["memory_view", "skill_list"]
    assert messages[0].tool_calls[0].arguments == {"key": "memory:user"}


def test_tool_results_project_onto_tool_messages(tmp_path):
    log = make_log(tmp_path)
    log.append("ctx_a", EventKind.TOOL_RESULT, {"call_id": "c1", "name": "exec", "content": "ok"})
    message = project(log.read("ctx_a"))[0]
    assert message.role == "tool"
    assert message.tool_call_id == "c1"
    assert message.name == "exec"


def test_boundary_events_become_system_messages(tmp_path):
    log = make_log(tmp_path)
    log.append("ctx_a", EventKind.BOUNDARY, {"text": "<toolset_change version=\"1->2\"/>"})
    message = project(log.read("ctx_a"))[0]
    assert message.role == "system"
    assert "toolset_change" in message.content


def test_empty_boundary_is_not_projected_as_a_blank_message(tmp_path):
    log = make_log(tmp_path)
    log.append("ctx_a", EventKind.BOUNDARY, {})
    assert project(log.read("ctx_a")) == []


def test_compact_supersedes_everything_before_it(tmp_path):
    log = make_log(tmp_path)
    for index in range(5):
        log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": f"turn {index}"})
    log.append("ctx_a", EventKind.COMPACT, {"summary": "we agreed on five turns"})
    log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "carry on"})
    messages = project(log.read("ctx_a"))
    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "we agreed on five turns" in messages[0].content
    assert messages[1].content == "carry on"


def test_superseded_events_stay_in_the_log(tmp_path):
    log = make_log(tmp_path)
    for index in range(5):
        log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": f"turn {index}"})
    compact(log, "ctx_a", lambda events: "summary")
    assert len(log.read("ctx_a")) == 6


def test_compact_keeps_boundaries_and_approvals_verbatim(tmp_path):
    log = make_log(tmp_path)
    log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "start"})
    log.append("ctx_a", EventKind.BOUNDARY, {"text": "toolset 1->2", "added": ["client_shell"]})
    log.append("ctx_a", EventKind.APPROVAL, {"tool": "exec", "decision": "pending"})
    event = compact(log, "ctx_a", lambda events: "summary")
    preserved = event.payload["preserved"]
    assert [item["kind"] for item in preserved] == ["boundary", "approval"]


def test_compact_records_what_it_covered(tmp_path):
    log = make_log(tmp_path)
    for index in range(3):
        log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": str(index)})
    event = compact(log, "ctx_a", lambda events: "s")
    assert event.payload["covered_until_seq"] == 2


def test_second_compact_does_not_resummarise_the_first(tmp_path):
    log = make_log(tmp_path)
    log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "one"})
    compact(log, "ctx_a", lambda events: "s1")
    log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "two"})
    seen: list[int] = []

    def summarizer(events: list[ContextEvent]) -> str:
        seen.extend(event.seq for event in events)
        return "s2"

    compact(log, "ctx_a", summarizer)
    assert seen == [2]


def test_compact_with_nothing_new_is_an_error(tmp_path):
    log = make_log(tmp_path)
    log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "one"})
    compact(log, "ctx_a", lambda events: "s1")
    with pytest.raises(ContextError):
        compact(log, "ctx_a", lambda events: "s2")


def test_compact_on_an_empty_context_is_an_error(tmp_path):
    with pytest.raises(ContextError):
        compact(make_log(tmp_path), "ctx_a", lambda events: "s")


def test_threshold_triggers_on_estimated_tokens(tmp_path):
    log = make_log(tmp_path)
    log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "x" * 400})
    policy = CompactionPolicy(window_tokens=100, threshold=0.5)
    assert should_compact(log.read("ctx_a"), policy)
    assert not should_compact(log.read("ctx_a"), CompactionPolicy(window_tokens=10_000))


def test_a_note_never_lands_between_a_tool_call_and_its_result(tmp_path):
    log = EventLog(path=tmp_path / "ctx.db")
    log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "run it"})
    log.append(
        "ctx_a",
        EventKind.TOOL_CALL,
        {"content": "", "calls": [{"id": "c1", "name": "exec", "arguments": {}}]}
    )
    log.append(
        "ctx_a",
        EventKind.APPROVAL,
        {"call_id": "c1", "tool": "exec", "text": "a human allowed this"}
    )
    log.append("ctx_a", EventKind.TOOL_RESULT, {"call_id": "c1", "name": "exec", "content": "ok"})
    messages = project(log.read("ctx_a"))
    assert [message.role for message in messages] == ["user", "assistant", "tool", "system"]
    assert messages[-1].content == "a human allowed this"
