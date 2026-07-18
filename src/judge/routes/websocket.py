"""
WebSocket 路由 — 实时战斗状态推送。

客户端连接 /ws/battle/{battle_id} 后，
在战斗事件发生时收到实时通知，替代 HTTP polling。
"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/battle/{battle_id}")
async def battle_websocket(websocket: WebSocket, battle_id: str, request: Request):
    """
    战斗 WebSocket 端点。

    流程:
      1. accept 连接
      2. 注册到 WebSocketManager
      3. 保持连接（接收 ping / 发送 pong）
      4. 断开时自动清理

    客户端收到推送后应调用 GET /battle-full 获取完整状态。
    """
    ws_manager = request.app.state.ws_manager

    await websocket.accept()
    await ws_manager.connect(battle_id, websocket)

    try:
        while True:
            # 接收客户端消息（ping 保活 / 任意消息）
            data = await websocket.receive_text()
            # 回应 pong 保活
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: battle={battle_id}")
    except Exception:
        logger.warning(f"WebSocket error: battle={battle_id}", exc_info=True)
    finally:
        await ws_manager.disconnect(battle_id, websocket)
