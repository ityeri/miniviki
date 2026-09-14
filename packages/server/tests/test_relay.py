import pytest
from miniviki.core.context import EventKind, EventLog
from miniviki.server import UnknownClientRequest
from miniviki.server.relay import pending_requests, record_result


def make_log(tmp_path) -> EventLog:
    return EventLog(path=tmp_path / "ctx.db")


def announce(log: EventLog, call_id: str = "c1") -> None:
    log.append(
        "ctx_a",
        EventKind.TOOL_REQUEST,
        {
            "call_id": call_id,
            "tool": "client_shell",
            "client_tool": "shell",
            "arguments": {"command": "ls"}
        }
    )


def results_of(log: EventLog) -> list[str]:
    return [
        event.payload["content"]
        for event in log.read("ctx_a")
        if event.kind is EventKind.TOOL_RESULT
    ]


def test_an_announced_call_is_pending_until_answered(tmp_path):
    log = make_log(tmp_path)
    announce(log)
    assert [request["call_id"] for request in pending_requests(log, "ctx_a")] == ["c1"]


def test_recording_a_result_writes_the_callers_name_back(tmp_path):
    """The result has to carry the toolset name or the projection loses the pair."""
    log = make_log(tmp_path)
    announce(log)
    assert record_result(log, "ctx_a", "c1", "file_a") is True
    assert pending_requests(log, "ctx_a") == []
    written = next(event for event in log.read("ctx_a") if event.kind is EventKind.TOOL_RESULT)
    assert written.payload["name"] == "client_shell"
    assert written.payload["content"] == "file_a"


def test_answering_twice_only_resolves_once(tmp_path):
    """Delivery is a replay, so a client answering twice is expected, not exotic."""
    log = make_log(tmp_path)
    announce(log)
    assert record_result(log, "ctx_a", "c1", "first") is True
    assert record_result(log, "ctx_a", "c1", "second") is False
    assert results_of(log) == ["first"]


def test_an_unknown_call_id_is_rejected(tmp_path):
    log = make_log(tmp_path)
    with pytest.raises(UnknownClientRequest):
        record_result(log, "ctx_a", "nope", "x")
