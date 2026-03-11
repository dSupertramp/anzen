from fastapi import APIRouter

from anzen.server.ws_manager import manager

router = APIRouter()


@router.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "ws_connections": manager.active_connections,
    }
