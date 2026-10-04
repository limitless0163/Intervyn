"""创建智能体 API，初始化观测并注册业务路由及健康检查。"""

from __future__ import annotations

from fastapi import FastAPI

from .api.router import router as api_router
from .core.config import get_settings
from .core.observability import init_observability


def create_app() -> FastAPI:
    # 每个进程初始化本地追踪及可选远程观测；未配置远程密钥时仍可使用本地追踪。
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
