from enum import StrEnum

from ..errors import HookDenied


class HookPermission(StrEnum):
    OBSERVE = "observe"
    MUTATE = "mutate"
    BLOCK = "block"


_RANK = {HookPermission.OBSERVE: 0, HookPermission.MUTATE: 1, HookPermission.BLOCK: 2}


def rank(permission: HookPermission) -> int:
    return _RANK[permission]


def require(declared: HookPermission, needed: HookPermission) -> None:
    """Observe is the default.

    Mutate and block must be declared up front, never discovered at runtime.
    """
    if rank(declared) < rank(needed):
        raise HookDenied(f"hook declared {declared} but attempted {needed}")
