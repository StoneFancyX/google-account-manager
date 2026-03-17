"""应用工厂 - FastAPI 应用 (RPC 版)"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from routers import auth, accounts, groups, dashboard, browser, automation, settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from services.browser import browser_manager
    await browser_manager.stop_all()


def create_app() -> FastAPI:
    app = FastAPI(title="谷歌账号管理器 (RPC)", version="0.5.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router,       prefix="/api/v1")
    app.include_router(dashboard.router,  prefix="/api/v1")
    app.include_router(accounts.router,   prefix="/api/v1")
    app.include_router(groups.router,     prefix="/api/v1")
    app.include_router(browser.router,   prefix="/api/v1")
    app.include_router(automation.router, prefix="/api/v1")
    app.include_router(automation.ws_router, prefix="/api/v1")
    app.include_router(settings.router,   prefix="/api/v1")

    return app


app = create_app()
