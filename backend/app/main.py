"""FastAPI application factory for the Intervyn agent API.

Exposes a health check plus the prep and score routers. ``main()`` runs the app
under uvicorn on the configured port.
"""

from __future__ import annotations

from fastapi import FastAPI

from .api.router import router as api_router
from .core.config import get_settings
from .core.observability import init_observability


def create_app() -> FastAPI:
    # Sync Settings (.env + env) into the tracer + Sentry/Langfuse once per
    # process. Idempotent; a no-op for hosted providers without keys, while
    # local JSONL tracing works out of the box (TRACE_ENABLED=0 disables).
    init_observability(get_settings())

    app = FastAPI(title="Intervyn Agent API")

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(api_router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run(app, host="0.0.0.0", port=settings.agent_api_port)


if __name__ == "__main__":
    main()
