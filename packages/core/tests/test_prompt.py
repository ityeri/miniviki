from miniviki.core.prompt import (
    AGENT_LAYER,
    CONTEXT_LAYER,
    GLOBAL_LAYER,
    SoulLayer,
    assemble,
    merge_souls,
    render_environment,
    render_index,
)
from miniviki.core.tools import Toolset, ToolSpec


def spec(name: str, description: str = "d", requires_approval: bool = False) -> ToolSpec:
    return ToolSpec(name=name, description=description, requires_approval=requires_approval)


def test_souls_merge_in_layer_order_not_argument_order():
    merged = merge_souls(
        [
            SoulLayer(name=CONTEXT_LAYER, body="context rules"),
            SoulLayer(name=GLOBAL_LAYER, body="global rules"),
            SoulLayer(name=AGENT_LAYER, body="agent rules")
        ]
    )
    order = [merged.index(text) for text in ("global rules", "agent rules", "context rules")]
    assert order == sorted(order)


def test_soul_layers_are_labelled_for_traceability():
    assert "<!-- soul:global -->" in merge_souls([SoulLayer(name=GLOBAL_LAYER, body="x")])


def test_empty_soul_layers_do_not_leave_blank_blocks():
    merged = merge_souls([SoulLayer(name=GLOBAL_LAYER, body="  "), SoulLayer(name=AGENT_LAYER)])
    assert merged == ""


def test_environment_is_generated_from_the_toolset():
    specs = [spec("exec", "runs a command"), spec("memory:view", "reads a key")]
    toolset = Toolset.from_specs(specs)
    rendered = render_environment(toolset)
    assert toolset.version in rendered
    assert "`exec` — runs a command" in rendered
    assert "`memory:view` — reads a key" in rendered


def test_environment_flags_tools_that_need_consent():
    toolset = Toolset.from_specs([spec("exec", requires_approval=True), spec("memory:view")])
    rendered = render_environment(toolset)
    assert "Needs approval before running: exec" in rendered


def test_environment_names_the_attached_client():
    toolset = Toolset.from_specs([spec("exec")], client_label="ramyon")
    assert "Attached client: ramyon" in render_environment(toolset)


def test_index_carries_names_only_never_bodies():
    body = "SECRET BODY THAT MUST NOT BE INLINED"
    rendered = render_index("Skills", ["ydpy — download pitfalls"])
    assert "ydpy — download pitfalls" in rendered
    assert body not in rendered


def test_index_of_nothing_is_empty():
    assert render_index("Skills", []) == ""


def test_assembled_digest_is_stable_for_identical_inputs():
    souls = [SoulLayer(name=GLOBAL_LAYER, body="be careful")]
    toolset = Toolset.from_specs([spec("exec")])
    first = assemble(souls, toolset)
    second = assemble(souls, toolset)
    assert first.digest == second.digest
    assert first.text == second.text


def test_assembled_digest_changes_when_the_toolset_changes():
    souls = [SoulLayer(name=GLOBAL_LAYER, body="be careful")]
    before = assemble(souls, Toolset.from_specs([spec("exec")]))
    after = assemble(souls, Toolset.from_specs([spec("exec"), spec("memory:view")]))
    assert before.digest != after.digest


def test_assembled_sections_skip_what_was_not_provided():
    souls = [SoulLayer(name=GLOBAL_LAYER, body="soul")]
    result = assemble(souls, Toolset.from_specs([spec("exec")]))
    assert result.sections == ("soul", "environment")
    assert "Memory summary" not in result.text


def test_memory_summary_is_included_when_provided():
    result = assemble(
        [SoulLayer(name=GLOBAL_LAYER, body="soul")],
        Toolset.from_specs([spec("exec")]),
        skill_index=["ydpy — download pitfalls"],
        memory_summary="user prefers PyCharm"
    )
    assert "user prefers PyCharm" in result.text
    assert "ydpy — download pitfalls" in result.text
    assert result.sections == ("soul", "environment", "skills", "memory")


def test_metadata_pins_the_toolset_version():
    toolset = Toolset.from_specs([spec("exec")])
    assert assemble([], toolset).metadata["toolset_version"] == toolset.version
