"""
PersistenceWorker — 后台持久化消费者。

订阅 BattleEvent，将状态变更异步写入飞书 Base。
所有 handler 返回 coroutine，由 AsyncEventBus 的消费者循环调度和 await。

不感知 HTTP / WebSocket。只依赖 BaseSync 和 CARDS_BY_ID。
"""

import logging
from typing import Dict, Any, Set, Optional

from engine.battle_manager import BattleManager
from engine.events import BattleEvent, BattleEventType, EventBus
from engine.card_library import CARDS_BY_ID
from integration.base_sync import BaseSync
from integration.snapshot_store import SnapshotStore

logger = logging.getLogger(__name__)


class PersistenceWorker:
    """
    持久化工作器。

    注册 7 种事件处理器到 EventBus。
    每个 handler 接收 BattleEvent，返回 Coroutine（BaseSync 方法调用）。
    AsyncEventBus 的 _consume_loop 负责 await 这些 coroutine。

    去重机制：通过 event_id 防止 retry 导致的重复写入。
    handler 成功完成后将 event_id 加入 _processed_events。
    失败时不加入集合，允许后续 retry。

    Phase 2: 在关键事件点保存 BattleSession snapshot。
    """

    def __init__(
        self,
        base_sync: BaseSync,
        snapshot_store: Optional[SnapshotStore] = None,
        battle_manager: Optional[BattleManager] = None,
    ):
        self._base_sync = base_sync
        self._snapshots = snapshot_store
        self._bm = battle_manager
        self._processed_events: Set[str] = set()

    def register(self, event_bus: EventBus) -> None:
        """在 EventBus 上注册所有事件处理器"""
        event_bus.subscribe(BattleEventType.BATTLE_CREATED,  self._on_battle_created)
        event_bus.subscribe(BattleEventType.BATTLE_RESTORED, self._on_battle_restored)
        event_bus.subscribe(BattleEventType.DECK_CONFIRMED,  self._on_deck_confirmed)
        event_bus.subscribe(BattleEventType.CARD_SUBMITTED,  self._on_card_submitted)
        event_bus.subscribe(BattleEventType.ROUND_RESOLVED,  self._on_round_resolved)
        event_bus.subscribe(BattleEventType.BATTLE_FINISHED, self._on_battle_finished)
        event_bus.subscribe(BattleEventType.BATTLE_ERROR,    self._on_battle_error)
        logger.info("PersistenceWorker registered 7 handlers")

    # ════════════════════════════════════════════════════
    # 事件处理器
    # ════════════════════════════════════════════════════

    async def _on_battle_created(self, event: BattleEvent) -> None:
        """
        对战初始化 → 写入可用牌列表 + 对战记录 + 玩家状态。

        顺序策略：先写独立数据（可用牌），最后写核心管理记录。
        确保中途失败时不会在 Base 中留下孤儿对战记录。
        """
        if not self._base_sync.enabled:
            return

        # 去重
        if event.event_id in self._processed_events:
            logger.warning(f"Skip duplicate event: {event.event_id} type={event.type.value}")
            return

        d = event.data

        # 1. 先写入双方可用卡牌（独立数据，非关键）
        for side, player_name, card_ids in [
            ("A", d["player_a_name"], d.get("player_a_available", [])),
            ("B", d["player_b_name"], d.get("player_b_available", [])),
        ]:
            cards = []
            for cid in card_ids:
                card = CARDS_BY_ID.get(cid)
                if card:
                    cards.append({
                        "id": card.id,
                        "name": card.name,
                        "category": card.category,
                        "aspect": card.aspect,
                    })
            if cards:
                await self._base_sync.sync_available_cards(
                    event.battle_id, side, player_name, cards,
                )

        # 2. 最后写入对战管理记录 + 玩家状态（核心数据）
        await self._base_sync.sync_battle_init(
            battle_id=event.battle_id,
            player_a_name=d["player_a_name"],
            player_b_name=d["player_b_name"],
            player_a_aspects=d["player_a_aspects"],
            player_b_aspects=d["player_b_aspects"],
        )

        # 所有写入成功后才标记已处理
        self._processed_events.add(event.event_id)
        # 保存初始快照
        self._save_snapshot(event)

    async def _on_battle_restored(self, event: BattleEvent) -> None:
        """会话恢复 — 仅记录日志，不写 Base（数据已在 Base 中）"""
        d = event.data
        logger.info(
            f"Battle restored: {event.battle_id} "
            f"type={d.get('restore_type', 'unknown')} "
            f"r={d.get('current_round', '?')} state={d.get('state', '?')}"
        )

    async def _on_deck_confirmed(self, event: BattleEvent) -> None:
        """牌库确认 → 更新对战状态为「对战中」"""
        if event.event_id in self._processed_events:
            logger.warning(f"Skip duplicate event: {event.event_id} type={event.type.value}")
            return
        await self._base_sync.sync_battle_started(battle_id=event.battle_id)
        self._processed_events.add(event.event_id)
        # 牌库锁定后保存快照
        self._save_snapshot(event)

    async def _on_card_submitted(self, event: BattleEvent) -> None:
        """出牌提交 → 写入提交记录 + 更新已提交标记"""
        if event.event_id in self._processed_events:
            logger.warning(f"Skip duplicate event: {event.event_id} type={event.type.value}")
            return
        d = event.data
        await self._base_sync.sync_submission_made(
            battle_id=event.battle_id,
            side=d["side"],
            player_name=d["player_name"],
            card_id=d["card_id"],
        )
        self._processed_events.add(event.event_id)

    async def _on_round_resolved(self, event: BattleEvent) -> None:
        """回合结算 → 写入对战记录 + 更新双方状态 + 回合进度"""
        if event.event_id in self._processed_events:
            logger.warning(f"Skip duplicate event: {event.event_id} type={event.type.value}")
            return
        d = event.data
        await self._base_sync.sync_round_result(
            battle_id=event.battle_id,
            round_number=d["round_number"],
            card_a_name=f"{d['card_a_id']} {d['card_a_name']}",
            card_b_name=f"{d['card_b_id']} {d['card_b_name']}",
            rps_description=d["rps_description"],
            damage_to_a=d["damage_to_a"],
            damage_to_b=d["damage_to_b"],
            hp_a_after=d["hp_a_after"],
            hp_b_after=d["hp_b_after"],
            special_events=d.get("special_events", []),
            winner=d.get("winner_side"),
            battle_ended=d.get("battle_ended", False),
            state_a=d.get("state_a_snapshot"),
            state_b=d.get("state_b_snapshot"),
        )
        self._processed_events.add(event.event_id)
        # 每 3 轮保存一次快照
        round_num = d.get("round_number", 0)
        if round_num % 3 == 0:
            self._save_snapshot(event)

    async def _on_battle_finished(self, event: BattleEvent) -> None:
        """
        对战结束 — 审计日志 + 清理 snapshot。

        ROUND_RESOLVED 的 sync_round_result 已处理 Base 持久化。
        此处做收尾清理：finished 对战不再需要 snapshot 用于恢复。
        """
        d = event.data
        logger.info(
            f"Battle finished: {event.battle_id} "
            f"winner={d.get('winner')} reason={d.get('end_reason')}"
        )
        # 清理 snapshot（finished battle 不再需要恢复，event_log 保留）
        if self._snapshots is not None:
            self._snapshots.delete(event.battle_id)

    async def _on_battle_error(self, event: BattleEvent) -> None:
        """状态变更异常 — 仅记录错误日志"""
        d = event.data
        logger.error(
            f"Battle error: {event.battle_id} "
            f"context={d.get('context')} error={d.get('error')}"
        )

    # ════════════════════════════════════════════════════
    # 快照保存
    # ════════════════════════════════════════════════════

    def _save_snapshot(self, event: BattleEvent) -> None:
        """保存 BattleSession 快照（best-effort，失败不影响主流程）"""
        if self._snapshots is None or self._bm is None:
            return
        try:
            session = self._bm._battles.get(event.battle_id)
            if session is None:
                return
            self._snapshots.save(session, last_event_id=event.event_id)
        except Exception:
            logger.warning(
                f"Snapshot save skipped for {event.battle_id}: "
                f"session may have been removed", exc_info=True
            )
