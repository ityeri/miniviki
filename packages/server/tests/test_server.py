from miniviki.core.llm import ScriptedClient, call, reply
from miniviki.server import Runtime
from server_support import collect, kinds, serve, tool_results


def build(tmp_path, script, **kwargs) -> Runtime:
    return Runtime.build(
        llm=ScriptedClient(script=list(script)),
        home=tmp_path / "home",
        **kwargs
    )


async def test_health_reports_no_live_contexts(tmp_path):
    async with serve(build(tmp_path, [])) as http:
        response = await http.get("/health")
        assert response.status_code == 200
        assert response.json() == {"ok": True, "live_contexts": 0}


async def test_create_context_returns_a_handle(tmp_path):
    async with serve(build(tmp_path, [])) as http:
        response = await http.post("/contexts", json={"kind": "main", "label": "work"})
        assert response.status_code == 200
        handle = response.json()
        assert handle["id"].startswith("ctx_")
        assert handle["kind"] == "main"
        assert handle["toolset_version"]
        assert handle["initial_context_digest"]


async def test_context_state_reads_back_the_same_handle(tmp_path):
    async with serve(build(tmp_path, [])) as http:
        created = (await http.post("/contexts", json={})).json()
        fetched = (await http.get(f"/contexts/{created['id']}")).json()
        assert fetched == created


async def test_a_provisioned_workspace_exists_on_disk(tmp_path):
    runtime = build(tmp_path, [])
    async with serve(runtime) as http:
        created = (await http.post("/contexts", json={})).json()
        workspace = runtime.layout.workspaces / created["id"]
        assert workspace.is_dir()


async def test_an_unknown_context_is_a_404(tmp_path):
    async with serve(build(tmp_path, [])) as http:
        assert (await http.get("/contexts/ctx_nope")).status_code == 404
        assert (await http.post("/contexts/ctx_nope/input", json={"text": "hi"})).status_code == 404


async def test_an_unknown_kind_is_a_400(tmp_path):
    async with serve(build(tmp_path, [])) as http:
        response = await http.post("/contexts", json={"kind": "banana"})
        assert response.status_code == 400
        assert "unknown context kind" in response.json()["detail"]


async def test_empty_input_is_rejected(tmp_path):
    async with serve(build(tmp_path, [])) as http:
        context_id = (await http.post("/contexts", json={})).json()["id"]
        response = await http.post(f"/contexts/{context_id}/input", json={"text": ""})
        assert response.status_code == 400


async def test_submit_streams_the_reply_through_to_run_end(tmp_path):
    runtime = build(tmp_path, [reply("hello there", prompt_tokens=12)])
    async with serve(runtime) as http:
        context_id = (await http.post("/contexts", json={})).json()["id"]
        submitted = await http.post(f"/contexts/{context_id}/input", json={"text": "hi"})
        assert submitted.status_code == 200
        assert submitted.json()["run_id"].startswith("run_")
        events = await collect(http, context_id)
    assert kinds(events) == ["message", "message", "run_end"]
    assert events[1]["payload"] == {"role": "assistant", "content": "hello there"}
    assert events[-1]["payload"]["status"] == "done"
    assert events[-1]["payload"]["prompt_tokens"] == 12


async def test_a_tool_call_round_trips_over_the_wire(tmp_path):
    script = [call("exec", {"command": "echo wire"}, call_id="c1"), reply("ran it")]
    async with serve(build(tmp_path, script)) as http:
        context_id = (await http.post("/contexts", json={})).json()["id"]
        await http.post(f"/contexts/{context_id}/input", json={"text": "run it"})
        events = await collect(http, context_id)
    assert kinds(events) == ["message", "tool_call", "tool_result", "message", "run_end"]
    assert events[1]["payload"]["calls"][0]["name"] == "exec"
    assert "wire" in tool_results(events)[0]


async def test_memory_survives_between_runs(tmp_path):
    script = [
        call("memory:write", {"key": "memory:user:ide", "body": "PyCharm"}, call_id="c1"),
        reply("saved"),
        call("memory:list", {}, call_id="c2"),
        reply("listed")
    ]
    async with serve(build(tmp_path, script)) as http:
        context_id = (await http.post("/contexts", json={})).json()["id"]
        await http.post(f"/contexts/{context_id}/input", json={"text": "remember my ide"})
        first = await collect(http, context_id)
        await http.post(f"/contexts/{context_id}/input", json={"text": "what do you know"})
        second = await collect(http, context_id, from_seq=first[-1]["seq"] + 1)
    assert "wrote memory:user:ide" in tool_results(first)[0]
    assert "memory:user:ide" in tool_results(second)[0]


async def test_a_sub_context_returns_only_its_answer(tmp_path):
    script = [
        call("context:spawn", {"prompt": "read the docs"}, call_id="c1"),
        reply("the docs say hello"),
        reply("parent done")
    ]
    async with serve(build(tmp_path, script)) as http:
        context_id = (await http.post("/contexts", json={})).json()["id"]
        await http.post(f"/contexts/{context_id}/input", json={"text": "delegate it"})
        events = await collect(http, context_id)
    assert tool_results(events) == ["the docs say hello"]


async def test_a_parked_approval_resumes_after_the_decision(tmp_path):
    script = [call("exec", {"command": "echo hi"}, call_id="c1"), reply("done")]
    runtime = build(tmp_path, script, exec_requires_approval=True)
    async with serve(runtime) as http:
        created = await http.post(
            "/contexts", json={"capabilities": {"approval_ui": True}}
        )
        context_id = created.json()["id"]
        await http.post(f"/contexts/{context_id}/input", json={"text": "run it"})
        parked = await collect(http, context_id)
        assert "approval_request" in kinds(parked)
        assert parked[-1]["payload"]["status"] == "waiting_approval"
        assert tool_results(parked) == []

        decided = await http.post(
            f"/contexts/{context_id}/approvals",
            json={"call_id": "c1", "decision": "approved"}
        )
        assert decided.status_code == 200
        resumed = await collect(http, context_id, from_seq=parked[-1]["seq"] + 1)
    assert kinds(resumed) == ["tool_result", "message", "run_end"]
    assert "hi" in tool_results(resumed)[0]
    assert resumed[-1]["payload"]["status"] == "done"


async def test_a_bad_decision_is_a_400(tmp_path):
    runtime = build(tmp_path, [], exec_requires_approval=True)
    async with serve(runtime) as http:
        context_id = (
            await http.post("/contexts", json={"capabilities": {"approval_ui": True}})
        ).json()["id"]
        response = await http.post(
            f"/contexts/{context_id}/approvals",
            json={"call_id": "c1", "decision": "maybe"}
        )
        assert response.status_code == 400


async def test_an_unknown_approval_is_a_404(tmp_path):
    runtime = build(tmp_path, [], exec_requires_approval=True)
    async with serve(runtime) as http:
        context_id = (await http.post("/contexts", json={})).json()["id"]
        response = await http.post(
            f"/contexts/{context_id}/approvals",
            json={"call_id": "c9", "decision": "approved"}
        )
        assert response.status_code == 404


async def test_a_client_without_an_approval_ui_loses_the_approval_tool(tmp_path):
    script = [call("exec", {"command": "rm -rf /"}, call_id="c1"), reply("gave up")]
    runtime = build(tmp_path, script, exec_requires_approval=True)
    async with serve(runtime) as http:
        context_id = (await http.post("/contexts", json={})).json()["id"]
        await http.post(f"/contexts/{context_id}/input", json={"text": "go"})
        events = await collect(http, context_id)
    assert "boundary" in kinds(events)
    assert "no approval ui" in events[0]["payload"]["text"]
    assert "no tool named 'exec'" in tool_results(events)[0]


async def test_declaring_client_tools_moves_the_toolset_version(tmp_path):
    described = {"name": "shell", "description": "run locally"}
    async with serve(build(tmp_path, [])) as http:
        bare = (await http.post("/contexts", json={})).json()
        with_tool = (await http.post("/contexts", json={"tools": [described]})).json()
        assert bare["toolset_version"] != with_tool["toolset_version"]

        updated = (
            await http.post(f"/contexts/{bare['id']}/tools", json={"tools": [described]})
        ).json()
        assert updated["toolset_version"] == with_tool["toolset_version"]

        reworded = (
            await http.post(
                f"/contexts/{bare['id']}/tools",
                json={"tools": [{"name": "shell", "description": "run a command"}]}
            )
        ).json()
    assert reworded["toolset_version"] != with_tool["toolset_version"]


async def test_updating_tools_notes_the_change_as_a_boundary(tmp_path):
    async with serve(build(tmp_path, [])) as http:
        context_id = (await http.post("/contexts", json={})).json()["id"]
        await http.post(f"/contexts/{context_id}/tools", json={"tools": [{"name": "shell"}]})
        events = await collect(http, context_id)
    assert "boundary" in kinds(events)
    assert "client:shell" in events[0]["payload"]["text"]


async def test_interrupt_reports_false_when_nothing_is_running(tmp_path):
    async with serve(build(tmp_path, [])) as http:
        context_id = (await http.post("/contexts", json={})).json()["id"]
        response = await http.post(f"/contexts/{context_id}/interrupt")
        assert response.json() == {"ok": False}


async def test_the_initial_context_digest_is_deterministic(tmp_path):
    async with serve(build(tmp_path, [])) as http:
        first = (await http.post("/contexts", json={})).json()
        second = (await http.post("/contexts", json={})).json()
    assert first["initial_context_digest"] == second["initial_context_digest"]
    assert first["id"] != second["id"]
