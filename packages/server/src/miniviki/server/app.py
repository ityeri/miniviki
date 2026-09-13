from fastapi import FastAPI

from .api.routes import build_router
from .bootstrap import Runtime
from .orchestration.runner import RunDriver
from .session import SessionRegistry


def create_app(runtime: Runtime) -> FastAPI:
    """Wire the runtime into an app. Nothing here knows about a specific front."""
    registry = SessionRegistry(runtime=runtime)
    driver = RunDriver(registry=registry)
    app = FastAPI(title="miniviki", version="0.1.0")
    app.state.runtime = runtime
    app.state.registry = registry
    app.state.driver = driver

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "live_contexts": len(registry.sessions)}

    app.include_router(build_router(registry, driver))
    return app
