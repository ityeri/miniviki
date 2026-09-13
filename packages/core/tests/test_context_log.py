from miniviki.core.context import EventKind, EventLog


def build(tmp_path) -> EventLog:
    return EventLog(path=tmp_path / "contexts.db")


def test_append_assigns_sequential_seq(tmp_path):
    log = build(tmp_path)
    first = log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": "hi"})
    second = log.append("ctx_a", EventKind.MESSAGE, {"role": "assistant", "content": "yo"})
    assert (first.seq, second.seq) == (0, 1)
    assert log.last_seq("ctx_a") == 1


def test_read_from_seq_skips_earlier_events(tmp_path):
    log = build(tmp_path)
    for index in range(3):
        log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": str(index)})
    tail = log.read("ctx_a", from_seq=1)
    assert [event.seq for event in tail] == [1, 2]


def test_read_honours_limit(tmp_path):
    log = build(tmp_path)
    for index in range(4):
        log.append("ctx_a", EventKind.MESSAGE, {"role": "user", "content": str(index)})
    assert len(log.read("ctx_a", limit=2)) == 2


def test_contexts_are_isolated(tmp_path):
    log = build(tmp_path)
    log.append("ctx_a", EventKind.MESSAGE, {"content": "a"})
    log.append("ctx_b", EventKind.MESSAGE, {"content": "b"})
    assert len(log.read("ctx_a")) == 1
    assert log.last_seq("ctx_b") == 0


def test_payload_round_trips_non_ascii(tmp_path):
    log = build(tmp_path)
    log.append("ctx_a", EventKind.MESSAGE, {"content": "안녕하세요 — 한글"})
    assert log.read("ctx_a")[0].payload["content"] == "안녕하세요 — 한글"


def test_log_is_append_only_there_is_no_update_or_delete(tmp_path):
    log = build(tmp_path)
    log.append("ctx_a", EventKind.MESSAGE, {"content": "first"})
    log.append("ctx_a", EventKind.MESSAGE, {"content": "second"})
    assert [event.payload["content"] for event in log.read("ctx_a")] == ["first", "second"]
