"""
WebSocketManager — 实时推送连接管理。

管理按 battle_id 分组的 WebSocket 连接。
负责 connect / disconnect / broadcast。
"""

import json
import logging
from typing import Dict, Set

from fastapi import WebSocket

from engine.events import BattleEvent

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    WebSocket 连接管理器。

    按 battle_id 分组管理连接：
      _connections: {battle_id: {websocket1, websocket2, ...}}

    broadcast 将事件推送给该 battle 的所有已连接客户端。
    单个连接失败不影响其他连接。
    """

    def __init__(self):
        self._connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, battle_id: str, websocket: WebSocket) -> None:
        """注册 WebSocket 连接"""
        if battle_id not in self._connections:
            self._connections[battle_id] = set()
        self._connections[battle_id].add(websocket)
        logger.info(
            f"WebSocket connected: battle={battle_id} "
            f"(total={len(self._connections[battle_id])})"
        )

    async def disconnect(self, battle_id: str, websocket: WebSocket) -> None:
        """移除 WebSocket 连接"""
        if battle_id in self._connections:
            self._connections[battle_id].discard(websocket)
            remaining = len(self._connections[battle_id])
            if remaining == 0:
                del self._connections[battle_id]
            else:
                logger.debug(
                    f"WebSocket disconnected: battle={battle_id} "
                    f"(remaining={remaining})"
                )

    async def broadcast(self, battle_id: str, event: BattleEvent) -> None:
        """
        推送事件给该 battle 的所有连接。

        消息格式: {"type": "...", "battle_id": "...", "data": {...}}

        单个连接失败：捕获异常 → 自动 disconnect → 不影响其他连接。
        """
        if battle_id not in self._connections:
            return

        message = json.dumps({
            "type": event.type.value,
            "battle_id": event.battle_id,
            "timestamp": event.timestamp,
            "data": event.data,
        }, ensure_ascii=False)

        dead_connections = []
        for ws in self._connections[battle_id]:
            try:
                await ws.send_text(message)
            except Exception:
                logger.warning(
                    f"WebSocket send failed: battle={battle_id}, "
                    f"marking for disconnect",
                    exc_info=True,
                )
                dead_connections.append(ws)

        # 清理已断开的连接
        for ws in dead_connections:
            await self.disconnect(battle_id, ws)
