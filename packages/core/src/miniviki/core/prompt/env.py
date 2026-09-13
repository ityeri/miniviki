from ..tools import Toolset


def render_environment(toolset: Toolset) -> str:
    """Built from the toolset, never hand written.

    This is the one section derived from the final composition, on purpose: if a
    human wrote it, it would eventually describe tools that no longer exist.
    """
    lines = ["# Environment", "", f"Toolset {toolset.version}. Tools callable right now:"]
    if toolset.specs:
        lines.extend(f"- `{spec.name}` — {spec.description}" for spec in toolset.specs)
    else:
        lines.append("- (none)")
    approvals = [spec.name for spec in toolset.specs if spec.requires_approval]
    if approvals:
        lines += ["", f"Needs approval before running: {', '.join(approvals)}"]
    if toolset.client_label:
        lines += ["", f"Attached client: {toolset.client_label}"]
    return "\n".join(lines)
