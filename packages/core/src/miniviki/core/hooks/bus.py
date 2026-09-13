from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .perm import HookPermission, require


@dataclass(slots=True)
class HookContext:
    listener: str
    payload: dict[str, Any] = field(default_factory=dict)
    permission: HookPermission = HookPermission.OBSERVE
    changes: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    blocked: str | None = None

    def set(self, key: str, value: Any) -> None:
        require(self.permission, HookPermission.MUTATE)
        self.payload[key] = value
        self.changes[key] = value

    def block(self, reason: str) -> None:
        require(self.permission, HookPermission.BLOCK)
        self.blocked = reason

    def note(self, text: str) -> None:
        self.notes.append(text)


Hook = Callable[[HookContext], None]


@dataclass(slots=True)
class Subscription:
    hook: Hook
    permission: HookPermission = HookPermission.OBSERVE


@dataclass(slots=True)
class HookBus:
    """The control plane. Hooks are not tools: the framework calls them, the agent never does."""

    subscriptions: dict[str, list[Subscription]] = field(default_factory=dict)

    def subscribe(
        self,
        listener: str,
        hook: Hook,
        permission: HookPermission = HookPermission.OBSERVE
    ) -> None:
        self.subscriptions.setdefault(listener, []).append(Subscription(hook, permission))

    def unsubscribe(self, listener: str, hook: Hook) -> None:
        remaining = [
            item for item in self.subscriptions.get(listener, []) if item.hook is not hook
        ]
        if remaining:
            self.subscriptions[listener] = remaining
        else:
            self.subscriptions.pop(listener, None)

    def listeners(self) -> tuple[str, ...]:
        return tuple(sorted(self.subscriptions))

    def publish(self, listener: str, payload: dict[str, Any] | None = None) -> HookContext:
        context = HookContext(listener=listener, payload=dict(payload or {}))
        for subscription in self.subscriptions.get(listener, []):
            context.permission = subscription.permission
            subscription.hook(context)
            if context.blocked is not None:
                break
        context.permission = HookPermission.OBSERVE
        return context
