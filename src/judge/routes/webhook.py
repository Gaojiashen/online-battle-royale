"""
Webhook处理器 — 接收Base自动化触发，路由到BattleManager
"""
import json
import logging
from models import WebhookPayload, WebhookResponse
from engine.battle_manager import BattleManager

logger = logging.getLogger(__name__)


class WebhookHandler:
    """处理来自Base自动化的webhook请求"""

    def __init__(self, battle_manager: BattleManager):
        self.battle_manager = battle_manager

    async def handle(self, payload: WebhookPayload) -> WebhookResponse:
        """
        处理webhook

        根据payload中的信息：
        1. 找到对应的对战
        2. 存储提交
        3. 如果双方都提交了，结算
        """
        logger.info(f"Webhook received: battle={payload.battle_id} "
                     f"round={payload.round_number} "
                     f"player={payload.player_name} card={payload.selected_card}")

        # 参数校验
        if not payload.battle_id:
            return WebhookResponse(status="error", message="缺少 battle_id")

        if not payload.selected_card:
            return WebhookResponse(status="error", message="缺少 selected_card")

        if payload.player_side not in ("a", "b"):
            return WebhookResponse(status="error",
                                   message=f"无效的 player_side: {payload.player_side}")

        # 路由到 BattleManager
        try:
            result = self.battle_manager.submit_card(
                battle_id=payload.battle_id,
                side=payload.player_side,
                card_id=payload.selected_card,
            )
            return result
        except Exception as e:
            logger.exception(f"Webhook处理失败: {e}")
            return WebhookResponse(
                battle_id=payload.battle_id,
                status="error",
                message=str(e),
            )
