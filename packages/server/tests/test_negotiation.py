
from miniviki.core.tools import CLIENT_NAMESPACE, ToolSpec
from miniviki.mca import ClientCapability, ClientTool
from miniviki.server.negotiation import RELAY_GAP, negotiate


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


async def test_a_client_tool_with_no_relay_says_so_instead_of_pretending():
    result = negotiate([], [ClientTool(name="shell")], ClientCapability())
    handler = result.toolset.get(f"{CLIENT_NAMESPACE}_shell").handler
    message = await handler()
    assert message == RELAY_GAP.format(name=f"{CLIENT_NAMESPACE}_shell")
    assert "exec" in message


def test_negotiation_never_adds_tools():
    base = [spec("exec"), spec("memory_view")]
    result = negotiate(base, [], ClientCapability(shell=True, filesystem=True, approval_ui=True))
    assert set(result.toolset.names()) == {"exec", "memory_view"}
