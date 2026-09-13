import pytest
from miniviki.core import ToolError, ToolNotFound
from miniviki.core.tools import ToolRegistry, Toolset, ToolSpec, namespace_of, validate_tool_name


def spec(
    name: str,
    description: str = "does a thing",
    client_scoped: bool = False,
    **kwargs
) -> ToolSpec:
    return ToolSpec(name=name, description=description, client_scoped=client_scoped, **kwargs)


def test_namespace_of_splits_on_the_separator():
    assert namespace_of("client:shell") == "client"
    assert namespace_of("exec") == ""


def test_registry_round_trip():
    registry = ToolRegistry()
    registry.register(spec("memory:view"))
    assert registry.names() == ["memory:view"]
    assert registry.get("memory:view").description == "does a thing"


def test_duplicate_registration_is_refused():
    registry = ToolRegistry()
    registry.register(spec("exec"))
    with pytest.raises(ToolError):
        registry.register(spec("exec"))


def test_unknown_tool_raises():
    with pytest.raises(ToolNotFound):
        ToolRegistry().get("exec")


@pytest.mark.parametrize(
    "name",
    ["", "memory:view:name.md", "memory:..:x", "memory:", ":memory", "us er"]
)
def test_invalid_tool_names_are_refused(name):
    with pytest.raises(ToolError):
        validate_tool_name(name)


def test_client_tool_must_live_in_the_client_namespace():
    with pytest.raises(ToolError):
        ToolRegistry().register(spec("shell", client_scoped=True))


def test_builtin_cannot_squat_the_client_namespace():
    with pytest.raises(ToolError):
        ToolRegistry().register(spec("client:exec"))


def test_injected_tools_only_enter_through_the_client_namespace():
    registry = ToolRegistry()
    registry.register(spec("exec"))
    merged = registry.with_client_tools([spec("client:shell", client_scoped=True)])
    assert merged.names() == ["client:shell", "exec"]
    assert registry.names() == ["exec"]
    with pytest.raises(ToolError):
        registry.with_client_tools([spec("shell")])


def test_toolset_version_is_stable_for_identical_specs():
    first = Toolset.from_specs([spec("exec"), spec("memory:view", "reads a key")])
    second = Toolset.from_specs([spec("memory:view", "reads a key"), spec("exec")])
    assert first.version == second.version


def test_toolset_version_ignores_the_handler():
    async def handler() -> str:
        return "x"

    async def other() -> str:
        return "y"

    first = Toolset.from_specs([spec("exec", handler=handler)])
    second = Toolset.from_specs([spec("exec", handler=other)])
    assert first.version == second.version


def test_toolset_version_changes_when_the_description_changes():
    first = Toolset.from_specs([spec("exec", "runs a command")])
    second = Toolset.from_specs([spec("exec", "runs a shell command")])
    assert first.version != second.version


def test_diff_classifies_every_tool():
    before = Toolset.from_specs([spec("exec"), spec("memory:view")])
    after = Toolset.from_specs([spec("exec"), spec("client:shell", client_scoped=True)])
    diff = before.diff(after)
    assert diff.added == ("client:shell",)
    assert diff.removed == ("memory:view",)
    assert diff.unchanged == ("exec",)
    assert not diff.is_empty()


def test_rendered_diff_names_removals_explicitly():
    before = Toolset.from_specs([spec("exec"), spec("client:shell", client_scoped=True)])
    after = Toolset.from_specs([spec("exec")])
    text = before.diff(after).render("7", "8", from_label="cli", to_label="web")
    assert "<toolset_change" in text
    assert 'version="7->8"' in text
    assert "  - client:shell" in text
    assert "no longer callable" in text
    assert "  = exec" in text


def test_result_budget_is_enforced_by_the_spec():
    tool = spec("exec", max_result_chars=10)
    result = tool.apply_budget("x" * 25)
    assert result.truncated
    assert result.content.startswith("x" * 10)
    assert "truncated: 15" in result.content


def test_result_within_budget_is_untouched():
    result = spec("exec", max_result_chars=100).apply_budget("short")
    assert result.content == "short"
    assert not result.truncated


def test_frozen_toolset_reports_a_useful_error():
    error = Toolset.from_specs([spec("exec")]).frozen_error()
    assert "pinned" in str(error)
