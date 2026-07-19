"""
WebSocket 路由 — 实时战斗状态推送。

客户端连接 /ws/battle/{battle_id} 后，
在战斗事件发生时收到实时通知，替代 HTTP polling。
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/battle/{battle_id}")
async def battle_websocket(websocket: WebSocket, battle_id: str):
    """
    战斗 WebSocket 端点。
    通过 websocket.app.state 获取 WebSocketManager。
    """
    ws_manager = websocket.app.state.ws_manager

    await websocket.accept()
    await ws_manager.connect(battle_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: battle={battle_id}")
    except Exception:
        logger.warning(f"WebSocket error: battle={battle_id}", exc_info=True)
    finally:
        await ws_manager.disconnect(battle_id, websocket)
