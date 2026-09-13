import pytest
from miniviki.core import HookDenied
from miniviki.core.hooks import (
    BEFORE_TOOL,
    DEFAULT_LISTENERS,
    RUN_END,
    HookBus,
    HookContext,
    HookPermission,
)


def test_observer_receives_the_payload():
    seen: list[HookContext] = []
    bus = HookBus()
    bus.subscribe(BEFORE_TOOL, seen.append)
    bus.publish(BEFORE_TOOL, {"tool": "exec"})
    assert seen[0].payload["tool"] == "exec"


def test_observer_cannot_mutate():
    bus = HookBus()

    def sneak(context: HookContext) -> None:
        context.set("tool", "rm")

    bus.subscribe(BEFORE_TOOL, sneak)
    with pytest.raises(HookDenied):
        bus.publish(BEFORE_TOOL, {"tool": "exec"})


def test_declared_mutator_can_change_the_payload_and_the_change_is_recorded():
    bus = HookBus()

    def add_approval(context: HookContext) -> None:
        context.set("requires_approval", True)

    bus.subscribe(BEFORE_TOOL, add_approval, permission=HookPermission.MUTATE)
    context = bus.publish(BEFORE_TOOL, {"tool": "exec"})
    assert context.payload["requires_approval"] is True
    assert context.changes == {"requires_approval": True}


def test_observer_that_forgets_to_declare_block_is_refused():
    bus = HookBus()
    bus.subscribe(BEFORE_TOOL, lambda context: context.block("nope"))
    with pytest.raises(HookDenied):
        bus.publish(BEFORE_TOOL, {})


def test_block_stops_the_chain_and_keeps_the_reason():
    bus = HookBus()
    reached: list[str] = []

    def guard(context: HookContext) -> None:
        context.block("dangerous command")

    bus.subscribe(BEFORE_TOOL, guard, permission=HookPermission.BLOCK)
    bus.subscribe(BEFORE_TOOL, lambda context: reached.append("second"))
    context = bus.publish(BEFORE_TOOL, {})
    assert context.blocked == "dangerous command"
    assert reached == []


def test_hooks_run_in_subscription_order():
    order: list[str] = []
    bus = HookBus()
    bus.subscribe(RUN_END, lambda context: order.append("first"))
    bus.subscribe(RUN_END, lambda context: order.append("second"))
    bus.publish(RUN_END)
    assert order == ["first", "second"]


def test_unsubscribe_removes_only_the_given_hook():
    calls: list[str] = []
    bus = HookBus()
    keep = lambda context: calls.append("keep")  # noqa: E731
    drop = lambda context: calls.append("drop")  # noqa: E731
    bus.subscribe(RUN_END, keep)
    bus.subscribe(RUN_END, drop)
    bus.unsubscribe(RUN_END, drop)
    bus.publish(RUN_END)
    assert calls == ["keep"]


def test_publishing_an_unsubscribed_listener_is_harmless():
    assert HookBus().publish(RUN_END).payload == {}


def test_default_listener_set_is_the_documented_one():
    assert set(DEFAULT_LISTENERS) == {
        "context:create",
        "before_llm",
        "after_llm",
        "before_tool",
        "after_tool",
        "on_compact",
        "run:end"
    }
