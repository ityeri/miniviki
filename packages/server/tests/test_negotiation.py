
from miniviki.core.tools import CLIENT_NAMESPACE, Toolset, ToolSpec
from miniviki.mca import ClientCapability, ClientTool
from miniviki.server.negotiation import negotiate


def spec(name: str, requires_approval: bool = False) -> ToolSpec:
    async def handler(**_arguments: object) -> str:
        return "ok"

    return ToolSpec(
        name=name,
        description="d",
        handler=handler,
        requires_approval=requires_approval
    )


def test_client_tools_are_qualified_into_the_client_namespace():
    result = negotiate([], [ClientTool(name="shell")], ClientCapability())
    assert result.toolset.names() == (f"{CLIENT_NAMESPACE}_shell",)


def test_a_client_tool_is_qualified_so_it_cannot_shadow_a_server_tool():
    result = negotiate([spec("exec")], [ClientTool(name="exec")], ClientCapability())
    assert set(result.toolset.names()) == {"exec", "client_exec"}
    assert result.summary() == "every requested capability was granted"


def test_two_declarations_of_the_same_client_tool_collide():
    tools = [ClientTool(name="shell"), ClientTool(name="client_shell")]
    result = negotiate([], tools, ClientCapability())
    assert result.toolset.names() == ("client_shell",)
    assert "already exists" in result.summary()


def test_approval_tools_are_dropped_without_an_approval_ui():
    result = negotiate([spec("exec", requires_approval=True)], [], ClientCapability())
    assert result.toolset.names() == ()
    assert "no approval ui" in result.summary()


def test_approval_tools_survive_when_the_client_offers_an_approval_ui():
    capability = ClientCapability(approval_ui=True)
    result = negotiate([spec("exec", requires_approval=True)], [], capability)
    assert result.toolset.names() == ("exec",)
    assert result.summary() == "every requested capability was granted"


def test_a_client_tool_is_marked_as_the_clients_to_run():
    """The flag is the whole mechanism: dispatch relays on it and nothing else."""
    result = negotiate([], [ClientTool(name="shell")], ClientCapability())
    declared = result.toolset.get(f"{CLIENT_NAMESPACE}_shell")
    assert declared.client_scoped is True
    assert declared.client_tool == "shell"
    assert declared.handler is None


def test_negotiation_never_adds_tools():
    base = [spec("exec"), spec("memory_view")]
    result = negotiate(base, [], ClientCapability(shell=True, filesystem=True, approval_ui=True))
    assert set(result.toolset.names()) == {"exec", "memory_view"}


def test_the_clients_own_name_for_a_tool_stays_out_of_the_fingerprint():
    """The model sees `client_shell`; whatever the client calls it is implementation."""
    plain = ToolSpec(name="client_shell", description="d", client_scoped=True)
    renamed = ToolSpec(
        name="client_shell",
        description="d",
        client_scoped=True,
        client_tool="something_else_entirely"
    )
    assert Toolset.from_specs([plain]).version == Toolset.from_specs([renamed]).version


def test_negotiation_carries_the_clients_label_into_the_toolset():
    """The label is what the environment section and a toolset boundary note name."""
    result = negotiate([], [], ClientCapability(label="ramyon"))
    assert result.toolset.client_label == "ramyon"

