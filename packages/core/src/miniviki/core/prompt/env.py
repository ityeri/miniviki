from ..tools import Toolset


def render_environment(toolset: Toolset) -> str:
    """Built from the toolset, never hand written.

    This is the one section derived from the final composition, on purpose: if a
    human wrote it, it would eventually describe tools that no longer exist.

    The topology lines are not decoration either. Without them the agent cannot tell
    that `exec` runs somewhere other than where the user is sitting, so a question
    about the user's files gets answered out of an empty workspace and reported as
    fact. They stay free of per-context values on purpose: this section is part of a
    digest that must not move when nothing the client declared has moved.
    """
    lines = ["# Environment", ""]
    lines += [
        "You run on the server, not on the machine the user is sitting at. `exec` runs",
        "inside your own workspace -- a temporary directory belonging to this context,",
        "not the user's filesystem. Run `pwd` if you need to name it.",
        ""
    ]
    if toolset.client_label:
        lines += [
            f"Attached client: {toolset.client_label} -- a separate machine. Tools",
            "that would run there are named `client_*`, and this build has no relay to",
            "them: the user's files and shell are out of reach. Say that plainly",
            "instead of approximating it with `exec`.",
            ""
        ]
    lines.append(f"Toolset {toolset.version}. Tools callable right now:")
    if toolset.specs:
        lines.extend(f"- `{spec.name}` — {spec.description}" for spec in toolset.specs)
    else:
        lines.append("- (none)")
    approvals = [spec.name for spec in toolset.specs if spec.requires_approval]
    if approvals:
        lines += ["", f"Needs approval before running: {', '.join(approvals)}"]
    return "\n".join(lines)
