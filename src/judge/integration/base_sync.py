"""
Base同步模块 — 将战斗状态写回飞书多维表格

使用 feishu_client 将战斗初始化、回合结果、玩家状态自动同步到统一Base。
"""
import os
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from integration.feishu_client import feishu_client

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════
# 配置 (从环境变量读取)
# ════════════════════════════════════════════════════

BASE_TOKEN = os.environ.get("FEISHU_BASE_TOKEN", "CB6XbtkLaafJnYsDL8RcHFpEnDg")

# 表ID
TABLE_BATTLE = "tblWciOhRlFFEaSr"          # 对战管理
TABLE_PLAYER_STATE = "tblTNAkesS7WlJoR"     # 玩家战斗状态
TABLE_BATTLE_LOG = "tblyUL90LNC1Snb5"       # 对战记录
TABLE_SUBMISSION = "tblcmGlzO76H3RQt"       # 回合提交
TABLE_AVAILABLE_CARDS = "tbl0DDzK6ckrqQah"  # 玩家可用牌


class BaseSync:
    """同步战斗数据到飞书Base"""

    def __init__(self, base_token: str = None):
        self.base_token = base_token or BASE_TOKEN
        self._enabled = bool(os.environ.get("FEISHU_APP_ID"))

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def sync_battle_init(
        self,
        battle_id: str,
        player_a_name: str,
        player_b_name: str,
        player_a_aspects: Dict[str, int],
        player_b_aspects: Dict[str, int],
    ):
        """写入对战管理表"""
        if not self.enabled:
            return

        import json
        try:
            await feishu_client.add_record(
                self.base_token,
                TABLE_BATTLE,
                {
                    "对战ID": battle_id,
                    "状态": "已初始化",
                    "玩家A名称": player_a_name,
                    "玩家B名称": player_b_name,
                    "玩家A性相等级": json.dumps(player_a_aspects, ensure_ascii=False),
                    "玩家B性相等级": json.dumps(player_b_aspects, ensure_ascii=False),
                    "当前回合": 0,
                    "创建时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                },
            )
            logger.info(f"Base同步: 对战 {battle_id} 已写入对战管理表")

            # 同时创建双方玩家状态记录
            for side, name in [("A", player_a_name), ("B", player_b_name)]:
                await feishu_client.add_record(
                    self.base_token,
                    TABLE_PLAYER_STATE,
                    {
                        "对战ID": battle_id,
                        "玩家侧": side,
                        "玩家名称": name,
                        "战HP": 20,
                        "锋芒": 0, "幻影": 0, "蓄力": 0,
                        "寒意": 0, "脉动": 0, "洞悉": 0, "看破": 0,
                        "已提交": False,
                    },
                )
            logger.info(f"Base同步: 玩家状态已初始化")

        except Exception as e:
            logger.error(f"Base同步失败 (init): {e}")

    async def sync_battle_started(self, battle_id: str):
        """对战开始（牌库确认后）"""
        if not self.enabled:
            return
        try:
            # 更新对战管理状态
            records = await feishu_client.list_records(
                self.base_token, TABLE_BATTLE
            )
            for r in records:
                fields = r.get("fields", {})
                if fields.get("对战ID") == battle_id:
                    await feishu_client.update_record(
                        self.base_token, TABLE_BATTLE, r["record_id"],
                        {"状态": "对战中", "当前回合": 1},
                    )
                    break
            logger.info(f"Base同步: 对战 {battle_id} 状态→对战中")
        except Exception as e:
            logger.error(f"Base同步失败 (start): {e}")

    async def sync_round_result(
        self,
        battle_id: str,
        round_number: int,
        card_a_name: str,
        card_b_name: str,
        rps_description: str,
        damage_to_a: int,
        damage_to_b: int,
        hp_a_after: int,
        hp_b_after: int,
        special_events: List[str],
        winner: Optional[str],
        battle_ended: bool,
        # 玩家资源状态
        state_a: Optional[Dict[str, int]] = None,
        state_b: Optional[Dict[str, int]] = None,
    ):
        """写入对战记录 + 更新玩家状态"""
        if not self.enabled:
            return
        try:
            # 1. 添加对战记录
            await feishu_client.add_record(
                self.base_token,
                TABLE_BATTLE_LOG,
                {
                    "对战ID": battle_id,
                    "回合编号": round_number,
                    "A使用卡牌": card_a_name,
                    "B使用卡牌": card_b_name,
                    "RPS结果描述": rps_description,
                    "A受到伤害": damage_to_a,
                    "B受到伤害": damage_to_b,
                    "A剩余HP": hp_a_after,
                    "B剩余HP": hp_b_after,
                    "特殊事件": "; ".join(special_events) if special_events else "",
                    "胜者": winner or "",
                },
            )
            logger.info(f"Base同步: 回合{round_number} 结果已写入对战记录")

            # 2. 更新玩家状态
            if state_a:
                await self._update_player_state(battle_id, "A", state_a)
            if state_b:
                await self._update_player_state(battle_id, "B", state_b)

            # 3. 如果战斗结束，更新对战管理；否则仅更新当前回合
            if battle_ended:
                await self._update_battle_finished(battle_id, winner, round_number)
            else:
                await self._sync_battle_round(battle_id, round_number)

        except Exception as e:
            logger.error(f"Base同步失败 (round): {e}")

    async def _sync_battle_round(self, battle_id: str, round_number: int):
        """更新对战管理表的当前回合字段"""
        records = await feishu_client.list_records(
            self.base_token, TABLE_BATTLE
        )
        for r in records:
            fields = r.get("fields", {})
            if fields.get("对战ID") == battle_id:
                await feishu_client.update_record(
                    self.base_token, TABLE_BATTLE, r["record_id"],
                    {"当前回合": round_number},
                )
                return

    async def _update_player_state(
        self, battle_id: str, side: str, resources: Dict[str, int]
    ):
        """更新玩家战斗状态记录"""
        records = await feishu_client.list_records(
            self.base_token, TABLE_PLAYER_STATE
        )
        for r in records:
            fields = r.get("fields", {})
            if fields.get("对战ID") == battle_id and fields.get("玩家侧") == side:
                update_fields = {
                    "战HP": resources.get("hp", 0),
                    "锋芒": resources.get("edge", 0),
                    "幻影": resources.get("phantom", 0),
                    "蓄力": resources.get("charge", 0),
                    "寒意": resources.get("chill", 0),
                    "脉动": resources.get("pulse", 0),
                    "洞悉": resources.get("read", 0),
                    "看破": resources.get("insight", 0),
                    "已提交": False,
                }
                await feishu_client.update_record(
                    self.base_token, TABLE_PLAYER_STATE, r["record_id"], update_fields
                )
                return

    async def _update_battle_finished(
        self, battle_id: str, winner: Optional[str], final_round: int
    ):
        """更新对战管理为已结束"""
        records = await feishu_client.list_records(
            self.base_token, TABLE_BATTLE
        )
        for r in records:
            fields = r.get("fields", {})
            if fields.get("对战ID") == battle_id:
                await feishu_client.update_record(
                    self.base_token, TABLE_BATTLE, r["record_id"],
                    {
                        "状态": "已结束",
                        "胜者": winner or "平局",
                        "当前回合": final_round,
                    },
                )
                break

    async def sync_submission_made(
        self, battle_id: str, side: str, player_name: str, card_id: str
    ):
        """记录提交到回合提交表"""
        if not self.enabled:
            return
        try:
            await feishu_client.add_record(
                self.base_token,
                TABLE_SUBMISSION,
                {
                    "对战ID": battle_id,
                    "玩家侧": side,
                    "玩家名称": player_name,
                    "选择的卡牌ID": card_id,
                    "提交时间": datetime.now().strftime("%H:%M:%S"),
                },
            )
            # 更新玩家状态中的已提交标记
            await self._set_submitted_flag(battle_id, side, True)
        except Exception as e:
            logger.error(f"Base同步失败 (submission): {e}")

    async def _set_submitted_flag(self, battle_id: str, side: str, submitted: bool):
        """更新玩家已提交标记"""
        records = await feishu_client.list_records(
            self.base_token, TABLE_PLAYER_STATE
        )
        for r in records:
            fields = r.get("fields", {})
            if fields.get("对战ID") == battle_id and fields.get("玩家侧") == side:
                await feishu_client.update_record(
                    self.base_token, TABLE_PLAYER_STATE, r["record_id"],
                    {"已提交": submitted},
                )
                return

    async def clear_submission_flags(self, battle_id: str):
        """回合结算后清除双方的已提交标记"""
        if not self.enabled:
            return
        await self._set_submitted_flag(battle_id, "A", False)
        await self._set_submitted_flag(battle_id, "B", False)

    async def sync_available_cards(
        self,
        battle_id: str,
        side: str,
        player_name: str,
        cards: List[Dict[str, str]],
    ):
        """写入玩家可用牌列表（批量写入）"""
        if not self.enabled:
            return
        try:
            records = [
                {
                    "对战ID": battle_id,
                    "玩家侧": side,
                    "卡牌ID": c["id"],
                    "卡牌名称": c["name"],
                    "类别": c["category"],
                    "性相": c["aspect"],
                }
                for c in cards
            ]
            count = await feishu_client.batch_add_records(
                self.base_token, TABLE_AVAILABLE_CARDS, records
            )
            logger.info(f"Base同步: {player_name}({side}) 可用牌 {count} 张已批量写入")
        except Exception as e:
            logger.error(f"Base同步失败 (available_cards): {e}")

    async def sync_deck_confirmed(
        self,
        battle_id: str,
        side: str,
        deck: List[str],
    ):
        """将选定的8张牌写入玩家战斗状态的牌位1-8，并标记已确认"""
        if not self.enabled:
            return
        try:
            records = await feishu_client.list_records(
                self.base_token, TABLE_PLAYER_STATE
            )
            for r in records:
                fields = r.get("fields", {})
                if fields.get("对战ID") == battle_id and fields.get("玩家侧") == side:
                    update = {"牌库已确认": True}
                    for i, card_id in enumerate(deck[:8], 1):
                        update[f"牌位{i}"] = card_id
                    await feishu_client.update_record(
                        self.base_token, TABLE_PLAYER_STATE, r["record_id"], update
                    )
                    logger.info(f"Base同步: {side} 牌库已确认 {deck}")
                    return
        except Exception as e:
            logger.error(f"Base同步失败 (deck_confirm): {e}")

    async def check_both_decks_confirmed(self, battle_id: str) -> bool:
        """检查双方是否都确认了牌库"""
        if not self.enabled:
            return True  # 如果没有Base同步，默认通过
        try:
            records = await feishu_client.list_records(
                self.base_token, TABLE_PLAYER_STATE
            )
            confirmed = []
            for r in records:
                fields = r.get("fields", {})
                if fields.get("对战ID") == battle_id:
                    confirmed.append(fields.get("牌库已确认", False))
            return len(confirmed) >= 2 and all(confirmed[:2])
        except Exception as e:
            logger.error(f"Base同步失败 (check_decks): {e}")
            return False


# 全局单例
base_sync = BaseSync()
