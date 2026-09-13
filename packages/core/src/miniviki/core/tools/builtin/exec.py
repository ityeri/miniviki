from miniviki.sandbox import Sandbox

from ..spec import ToolSpec

_EXEC_PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "Shell command to run inside the workspace."},
        "timeout": {"type": "number", "description": "Seconds before the command is killed."}
    },
    "required": ["command"]
}


def build_exec_tool(
    sandbox: Sandbox,
    default_timeout: float = 30.0,
    requires_approval: bool = False
) -> ToolSpec:
    """Run commands inside the provisioned sandbox, never on the server host.

    The trust boundary is the whole point: this tool and a client's shell tool are
    different domains, so they never share a name or an approval policy.
    """

    async def run(command: str, timeout: float | None = None) -> str:
        result = await sandbox.exec(command, timeout=timeout or default_timeout)
        lines = [f"exit_code: {result.exit_code}"]
        if result.timed_out:
            lines.append("timed_out: true")
        if result.stdout.strip():
            lines.append(f"stdout:\n{result.stdout.rstrip()}")
        if result.stderr.strip():
            lines.append(f"stderr:\n{result.stderr.rstrip()}")
        return "\n".join(lines)

    return ToolSpec(
        name="exec",
        description=(
            "Run a shell command in the agent workspace and get exit code, stdout and stderr. "
            "The workspace is ephemeral and owned by this agent."
        ),
        parameters=_EXEC_PARAMETERS,
        handler=run,
        requires_approval=requires_approval
    )
