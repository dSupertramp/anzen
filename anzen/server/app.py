"""
Anzen Dashboard — FastAPI server.
Receives guard events from the SDK, persists them, streams to the
dashboard via WebSocket, and serves the pre-built frontend SPA from ui/.
"""

import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from anzen.server.config import settings
from anzen.server.database import init_db
from anzen.server.routers import events, health, sessions, stats, websocket

# Frontend served exclusively from the repo's ui folder (Vite build: ui/frontend/dist)
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_UI_DIR = _PROJECT_ROOT / "ui"
_UI_STATIC = _UI_DIR / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Anzen",
        description="Open-source security layer for agentic AI",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(events.router, prefix="/api")
    app.include_router(websocket.router, prefix="/api")
    app.include_router(stats.router, prefix="/api")
    app.include_router(sessions.router, prefix="/api")

    if _UI_STATIC.is_dir():
        index_html = _UI_STATIC / "index.html"
        assets_dir = _UI_STATIC / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="static-assets")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            file_path = (_UI_STATIC / full_path).resolve()
            if not str(file_path).startswith(str(_UI_STATIC.resolve())):
                return FileResponse(index_html)  # path traversal → SPA
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(index_html)

    return app


app = create_app()
