"""
WebSocket /api/ws — real-time event stream to dashboard.
"""

import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from anzen.server.ws_manager import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # Send ping every 30s to keep connection alive
        while True:
            await asyncio.sleep(30)
            try:
                await ws.send_text('{"type":"ping"}')
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws)
