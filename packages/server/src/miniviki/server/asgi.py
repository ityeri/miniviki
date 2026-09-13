from fastapi import FastAPI

from .app import create_app
from .hosting import build_runtime


def app() -> FastAPI:
    """ASGI factory. Point any ASGI server at `miniviki.server.asgi:app`.

    Which server runs this is a deployment decision, so none is named here.
    """
    return create_app(build_runtime())
