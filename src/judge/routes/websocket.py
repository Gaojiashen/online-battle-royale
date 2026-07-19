"""
WebSocket 路由 — 实时战斗状态推送。

客户端连接 /ws/battle/{battle_id} 后，
在战斗事件发生时收到实时通知，替代 HTTP polling。
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# 由 app.py lifespan 注入
_ws_manager = None


def set_ws_manager(mgr):
    global _ws_manager
    _ws_manager = mgr


@router.websocket("/ws/battle/{battle_id}")
async def battle_websocket(websocket: WebSocket, battle_id: str):
    """
    战斗 WebSocket 端点。
    """
    if _ws_manager is None:
        await websocket.close(code=1011, reason="WebSocketManager not initialized")
        return

    await websocket.accept()
    await _ws_manager.connect(battle_id, websocket)

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
        await _ws_manager.disconnect(battle_id, websocket)
