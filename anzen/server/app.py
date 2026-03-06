"""
Anzen Dashboard — FastAPI server.
Receives guard events from the SDK, persists them, streams to the
dashboard via WebSocket, and serves the pre-built frontend SPA.
"""

import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import FileResponse

from anzen.server.routers import events, websocket, stats, sessions, health
from anzen.server.database import init_db
from anzen.server.config import settings

_STATIC_DIR = pathlib.Path(__file__).parent / "_static"


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

    if _STATIC_DIR.is_dir():
        index_html = _STATIC_DIR / "index.html"

        app.mount("/assets", StaticFiles(directory=_STATIC_DIR / "assets"), name="static-assets")
        app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static-root")

        @app.get("/{full_path:path}")
        async def spa_fallback(full_path: str):
            file_path = _STATIC_DIR / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(index_html)

    return app


app = create_app()
