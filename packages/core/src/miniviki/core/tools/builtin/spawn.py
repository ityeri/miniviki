from collections.abc import Awaitable, Callable

from ..spec import ToolSpec

Spawner = Callable[[str, str, str], Awaitable[str]]


def build_spawn_tool(spawner: Spawner, requires_approval: bool = False) -> ToolSpec:
    """Start a child context and keep only its answer.

    A sub-context is a compressor, not a helper: the parent gets a summary and
    never the transcript, which is what buys back context budget.
    """

    async def spawn(prompt: str, kind: str = "subagent", mode: str = "fresh") -> str:
        return await spawner(prompt, kind, mode)

    return ToolSpec(
        name="context_spawn",
        description=(
            "Run a task in a separate context and get back only its final answer. "
            "Use it for bulk exploration you do not want in this context."
        ),
        parameters={
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "What the child should do."},
                "kind": {
                    "type": "string",
                    "enum": ["subagent", "quick", "fork"],
                    "description": "subagent reads from scratch, quick is one-shot, fork inherits."
                },
                "mode": {
                    "type": "string",
                    "enum": ["fresh", "inherit"],
                    "description": "Context to start from."
                }
            },
            "required": ["prompt"]
        },
        handler=spawn,
        requires_approval=requires_approval
    )
