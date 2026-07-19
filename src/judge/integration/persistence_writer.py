"""
PostgresWriter — PostgreSQL 写入调度器。

PersistenceWorker 将 BattleEvent 委托给 PostgresWriter，
PostgresWriter 再转发给 PostgresSync 写入 PostgreSQL。
"""

import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


class PostgresWriter:
    """PostgreSQL 写入器。"""

    def __init__(self, postgres_sync=None):
        self._pg = postgres_sync

    @property
    def enabled(self) -> bool:
        return self._pg is not None and self._pg.enabled

    # ════════════════════════════════════════════════════
    # 公开接口
    # ════════════════════════════════════════════════════

    async def sync_battle_init(self, battle_id, player_a_name, player_b_name,
                               player_a_aspects, player_b_aspects):
        await self._write("sync_battle_init",
            battle_id=battle_id, player_a_name=player_a_name,
            player_b_name=player_b_name, player_a_aspects=player_a_aspects,
            player_b_aspects=player_b_aspects)

    async def sync_available_cards(self, battle_id, side, player_name, cards):
        await self._write("sync_available_cards",
            battle_id=battle_id, side=side, player_name=player_name, cards=cards)

    async def sync_battle_started(self, battle_id):
        await self._write("sync_battle_started", battle_id=battle_id)

    async def sync_submission_made(self, battle_id, side, player_name, card_id):
        await self._write("sync_submission_made",
            battle_id=battle_id, side=side, player_name=player_name, card_id=card_id)

    async def sync_round_result(self, battle_id, round_number, card_a_name,
                                card_b_name, rps_description, damage_to_a,
                                damage_to_b, hp_a_after, hp_b_after,
                                special_events, winner, battle_ended,
                                state_a=None, state_b=None):
        await self._write("sync_round_result",
            battle_id=battle_id, round_number=round_number,
            card_a_name=card_a_name, card_b_name=card_b_name,
            rps_description=rps_description,
            damage_to_a=damage_to_a, damage_to_b=damage_to_b,
            hp_a_after=hp_a_after, hp_b_after=hp_b_after,
            special_events=special_events, winner=winner,
            battle_ended=battle_ended,
            state_a=state_a, state_b=state_b)

    async def sync_deck_confirmed(self, battle_id, side, deck):
        await self._write("sync_deck_confirmed",
            battle_id=battle_id, side=side, deck=deck)

    async def check_both_decks_confirmed(self, battle_id: str) -> bool:
        if not self.enabled:
            return True
        try:
            return await self._pg.check_both_decks_confirmed(battle_id)
        except Exception:
            logger.warning(
                f"PostgresWriter: check_decks failed {battle_id}", exc_info=True
            )
            return True

    async def clear_submission_flags(self, battle_id: str):
        await self._write("clear_submission_flags", battle_id=battle_id)

    # ════════════════════════════════════════════════════
    # 内部
    # ════════════════════════════════════════════════════

    async def _write(self, method_name: str, **kwargs):
        if not self.enabled:
            return
        try:
            method = getattr(self._pg, method_name)
            await method(**kwargs)
        except Exception:
            logger.error(
                f"PostgresWriter: PostgresSync.{method_name} failed",
                exc_info=True,
            )
