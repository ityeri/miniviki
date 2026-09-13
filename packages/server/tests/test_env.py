import os
from pathlib import Path

from miniviki.core.llm import EchoClient
from miniviki.server import build_runtime, load_env_files


def write_env(directory: Path, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".env"
    path.write_text(body, encoding="utf-8")
    return path


def test_a_home_env_file_is_loaded(tmp_path, monkeypatch):
    home = tmp_path / "home"
    env_file = write_env(home, "MINIVIKI_TEST_A=from-file\n")
    monkeypatch.setenv("MINIVIKI_HOME", str(home))
    monkeypatch.delenv("MINIVIKI_TEST_A", raising=False)
    layout, loaded = load_env_files(cwd=tmp_path / "elsewhere")
    assert layout.root == home
    assert loaded == (env_file,)
    assert os.environ["MINIVIKI_TEST_A"] == "from-file"


def test_a_missing_env_file_is_not_an_error(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("MINIVIKI_HOME", str(home))
    layout, loaded = load_env_files(cwd=tmp_path / "nowhere")
    assert layout.root == home
    assert loaded == ()


def test_the_real_environment_is_never_overridden(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_env(home, "MINIVIKI_TEST_B=from-file\n")
    monkeypatch.setenv("MINIVIKI_HOME", str(home))
    monkeypatch.setenv("MINIVIKI_TEST_B", "from-shell")
    load_env_files(cwd=tmp_path / "elsewhere")
    assert os.environ["MINIVIKI_TEST_B"] == "from-shell"


def test_the_working_directory_wins_over_the_home(tmp_path, monkeypatch):
    work = tmp_path / "work"
    home = tmp_path / "home"
    write_env(work, "MINIVIKI_TEST_C=from-cwd\n")
    write_env(home, "MINIVIKI_TEST_C=from-home\n")
    monkeypatch.setenv("MINIVIKI_HOME", str(home))
    monkeypatch.delenv("MINIVIKI_TEST_C", raising=False)
    load_env_files(cwd=work)
    assert os.environ["MINIVIKI_TEST_C"] == "from-cwd"


def test_a_working_directory_env_can_point_at_the_home(tmp_path, monkeypatch):
    work = tmp_path / "work"
    chosen = tmp_path / "chosen"
    chosen.mkdir()
    env_file = write_env(work, f"MINIVIKI_HOME={chosen}\n")
    monkeypatch.delenv("MINIVIKI_HOME", raising=False)
    layout, loaded = load_env_files(cwd=work)
    assert layout.root == chosen
    assert loaded == (env_file,)


def test_both_locations_are_loaded(tmp_path, monkeypatch):
    work = tmp_path / "work"
    home = tmp_path / "home"
    working_file = write_env(work, "MINIVIKI_TEST_D=from-cwd\n")
    home_file = write_env(home, "MINIVIKI_TEST_E=from-home\n")
    monkeypatch.setenv("MINIVIKI_HOME", str(home))
    monkeypatch.delenv("MINIVIKI_TEST_D", raising=False)
    monkeypatch.delenv("MINIVIKI_TEST_E", raising=False)
    _layout, loaded = load_env_files(cwd=work)
    assert set(loaded) == {working_file, home_file}
    assert os.environ["MINIVIKI_TEST_D"] == "from-cwd"
    assert os.environ["MINIVIKI_TEST_E"] == "from-home"


def test_boot_reads_the_env_file(tmp_path, monkeypatch):
    home = tmp_path / "home"
    write_env(home, "MINIVIKI_LLM=echo\n")
    monkeypatch.setenv("MINIVIKI_HOME", str(home))
    monkeypatch.delenv("MINIVIKI_LLM", raising=False)
    monkeypatch.chdir(tmp_path)
    runtime = build_runtime()
    try:
        assert isinstance(runtime.llm, EchoClient)
        assert runtime.layout.root == home
    finally:
        runtime.aclose()
