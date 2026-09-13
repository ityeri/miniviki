
from miniviki.sandbox import ExecResult, LocalSandboxProvider, Sandbox, SandboxProvider, SandboxSpec


async def test_local_provider_satisfies_protocol():
    assert isinstance(LocalSandboxProvider(), SandboxProvider)


async def test_provisioned_sandbox_satisfies_protocol():
    sandbox = await LocalSandboxProvider().provision(SandboxSpec())
    assert isinstance(sandbox, Sandbox)


async def test_exec_captures_stdout():
    sandbox = await LocalSandboxProvider().provision(SandboxSpec())
    result = await sandbox.exec("echo hello")
    assert result.ok
    assert result.stdout.strip() == "hello"
    assert result.stderr == ""


async def test_exec_captures_stderr_separately():
    sandbox = await LocalSandboxProvider().provision(SandboxSpec())
    result = await sandbox.exec("echo oops 1>&2")
    assert result.ok
    assert result.stdout == ""
    assert result.stderr.strip() == "oops"


async def test_exec_reports_nonzero_exit():
    sandbox = await LocalSandboxProvider().provision(SandboxSpec())
    result = await sandbox.exec("exit 3")
    assert result.exit_code == 3
    assert not result.ok


async def test_exec_times_out_instead_of_hanging():
    sandbox = await LocalSandboxProvider().provision(SandboxSpec())
    result = await sandbox.exec("sleep 5", timeout=0.2)
    assert result.timed_out
    assert not result.ok


async def test_exec_runs_inside_the_provisioned_root(tmp_path):
    sandbox = await LocalSandboxProvider().provision(SandboxSpec(root_dir=str(tmp_path)))
    await sandbox.exec("touch marker")
    assert (tmp_path / "marker").exists()


async def test_stream_yields_output_as_it_arrives():
    sandbox = await LocalSandboxProvider().provision(SandboxSpec())
    chunks = [chunk async for chunk in sandbox.stream("printf 'alpha\\nbeta\\n'")]
    joined = "".join(chunks)
    assert "alpha" in joined
    assert "beta" in joined


async def test_spec_env_is_visible_to_commands():
    spec = SandboxSpec(env={"MINIVIKI_PROBE": "yes"})
    sandbox = await LocalSandboxProvider().provision(spec)
    result = await sandbox.exec("echo $MINIVIKI_PROBE")
    assert result.stdout.strip() == "yes"


async def test_unenforceable_limits_are_reported_not_silently_ignored():
    spec = SandboxSpec(cpu_limit=1.0, network=False)
    sandbox = await LocalSandboxProvider().provision(spec)
    assert set(sandbox.unenforced) == {"cpu_limit", "network"}


async def test_exec_result_round_trips_through_json():
    raw = {"exit_code": 0, "stdout": "hi", "stderr": "", "timed_out": False}
    assert ExecResult.from_json(raw) == ExecResult(exit_code=0, stdout="hi", stderr="")
