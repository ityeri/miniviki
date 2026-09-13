from pathlib import Path

from dotenv import load_dotenv

from .bootstrap import HomeLayout

ENV_FILE = ".env"


def load_env_files(cwd: Path | None = None) -> tuple[HomeLayout, tuple[Path, ...]]:
    """Load `.env` files and resolve the home layout from the result.

    The working directory is read first, so a `.env` sitting next to a project
    can point MINIVIKI_HOME somewhere; the home directory's own file is read
    after that. Real environment variables always win over both -- configuration
    injected into a container must not be silently replaced by a file someone
    happened to leave lying in a directory.
    """
    search = Path.cwd() if cwd is None else Path(cwd)
    loaded: list[Path] = []
    working_file = search / ENV_FILE
    if working_file.is_file():
        load_dotenv(working_file, override=False)
        loaded.append(working_file)
    layout = HomeLayout.resolve()
    home_file = layout.root / ENV_FILE
    if home_file not in loaded and home_file.is_file():
        load_dotenv(home_file, override=False)
        loaded.append(home_file)
    return layout, tuple(loaded)
