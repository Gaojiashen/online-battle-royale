"""
PostgresSync — PostgreSQL 持久化同步层。

使用 asyncpg 连接池执行参数化 SQL。
每个写操作保证事务一致性。
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import asyncpg

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════
# 配置
# ════════════════════════════════════════════════════

DATABASE_URL = os.environ.get("DATABASE_URL", "")


class PostgresSync:
    """
    PostgreSQL 同步层。

    公开接口与 PersistenceWriter 完全一致。
    enabled 属性由 DATABASE_URL 环境变量控制：
    - 未设置 → no-op
    - 已设置 → 写入 PostgreSQL
    """

    def __init__(self, pool: Optional[asyncpg.Pool] = None):
        self._pool = pool

    @property
    def enabled(self) -> bool:
        return self._pool is not None

    # ════════════════════════════════════════════════════
    # sync_battle_init
    # ════════════════════════════════════════════════════

    async def sync_battle_init(
        self,
        battle_id: str,
        player_a_name: str,
        player_b_name: str,
        player_a_aspects: Dict[str, int],
        player_b_aspects: Dict[str, int],
    ):
        """写入 battles + battle_players（一个事务）"""
        if not self.enabled:
            return

        now = datetime.now(timezone.utc)
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    # 1. 插入对战记录
                    await conn.execute(
                        """
                        INSERT INTO battles (battle_id, player_a_name, player_b_name,
                            player_a_aspects, player_b_aspects, state, current_round,
                            created_at, updated_at)
                        VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, '已初始化', 0, $6, $6)
                        ON CONFLICT (battle_id) DO NOTHING
                        """,
                        battle_id,
                        player_a_name,
                        player_b_name,
                        json.dumps(player_a_aspects, ensure_ascii=False),
                        json.dumps(player_b_aspects, ensure_ascii=False),
                        now,
                    )

                    # 2. 插入双方玩家战斗状态
                    for side, name in [("A", player_a_name), ("B", player_b_name)]:
                        await conn.execute(
                            """
                            INSERT INTO battle_players (battle_id, side, player_name,
                                hp, max_hp, edge, phantom, charge, chill, pulse, read, insight,
                                deck_slots, deck_confirmed, submitted, created_at, updated_at)
                            VALUES ($1, $2, $3, 20, 20, 0, 0, 0, 0, 0, 0, 0,
                                '[]'::jsonb, FALSE, FALSE, $4, $4)
                            ON CONFLICT (battle_id, side) DO NOTHING
                            """,
                            battle_id,
                            side,
                            name,
                            now,
                        )

            logger.info(f"PG sync: battle {battle_id} initialized")
        except Exception as e:
            logger.error(f"PG sync failed (init): battle={battle_id} error={e}")
            raise

    # ════════════════════════════════════════════════════
    # sync_available_cards
    # ════════════════════════════════════════════════════

    async def sync_available_cards(
        self,
        battle_id: str,
        side: str,
        player_name: str,
        cards: List[Dict[str, str]],
    ):
        """
        可用卡牌 — 不写入数据库。

        设计决策：可用卡牌由 battles.player_*_aspects JSONB
        + card_library.calculate_available() 实时计算。
        不需要持久化冗余数据。
        """
        if not self.enabled:
            return
        logger.debug(
            f"PG sync: available_cards skipped (computed on read) "
            f"battle={battle_id} side={side} count={len(cards)}"
        )

    # ════════════════════════════════════════════════════
    # sync_battle_started
    # ════════════════════════════════════════════════════

    async def sync_battle_started(self, battle_id: str):
        """对战开始 — 更新 battles 状态"""
        if not self.enabled:
            return

        now = datetime.now(timezone.utc)
        try:
            result = await self._pool.execute(
                """
                UPDATE battles
                SET state = '对战中', current_round = 1, updated_at = $2
                WHERE battle_id = $1
                """,
                battle_id,
                now,
            )
            # 检查是否更新了行
            if result == "UPDATE 0":
                logger.warning(
                    f"PG sync: battle_started — no row for {battle_id}"
                )
            else:
                logger.info(f"PG sync: battle {battle_id} state → in_progress")
        except Exception as e:
            logger.error(
                f"PG sync failed (start): battle={battle_id} error={e}"
            )
            raise

    # ════════════════════════════════════════════════════
    # sync_submission_made
    # ════════════════════════════════════════════════════

    async def sync_submission_made(
        self,
        battle_id: str,
        side: str,
        player_name: str,
        card_id: str,
    ):
        """出牌提交 — 写入 battle_submissions + 更新 battle_players"""
        if not self.enabled:
            return

        now = datetime.now(timezone.utc)
        try:
            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    # 1. 插入提交记录
                    await conn.execute(
                        """
                        INSERT INTO battle_submissions
                            (battle_id, side, player_name, card_id, round_number, created_at)
                        SELECT $1, $2, $3, $4, battles.current_round, $5
                        FROM battles
                        WHERE battles.battle_id = $1
                        """,
                        battle_id,
                        side,
                        player_name,
                        card_id,
                        now,
                    )

                    # 2. 更新已提交标记
                    result = await conn.execute(
                        """
                        UPDATE battle_players
                        SET submitted = TRUE, updated_at = $3
                        WHERE battle_id = $1 AND side = $2
                        """,
                        battle_id,
                        side,
                        now,
                    )
                    if result == "UPDATE 0":
                        logger.warning(
                            f"PG sync: submission_made — no battle_player "
                            f"row for {battle_id}/{side}"
                        )

            logger.info(
                f"PG sync: {player_name}({side}) submitted {card_id} "
                f"in {battle_id}"
            )
        except Exception as e:
            logger.error(
                f"PG sync failed (submission): battle={battle_id} "
                f"side={side} card={card_id} error={e}"
            )
            raise

    # ════════════════════════════════════════════════════
    # sync_round_result
    # ════════════════════════════════════════════════════

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
        state_a: Optional[Dict[str, int]] = None,
        state_b: Optional[Dict[str, int]] = None,
    ):
        """回合结算 — 写入 battle_rounds + 更新 battle_players + battles"""
        if not self.enabled:
            return

        now = datetime.now(timezone.utc)
        try:
            # 解析 card_a_id / card_b_id（格式: "B01 劈斩"）
            card_a_id = card_a_name.split(" ")[0] if card_a_name else ""
            card_b_id = card_b_name.split(" ")[0] if card_b_name else ""

            async with self._pool.acquire() as conn:
                async with conn.transaction():
                    # 1. 插入回合记录
                    await conn.execute(
                        """
                        INSERT INTO battle_rounds
                            (battle_id, round_number, card_a_id, card_a_name,
                             card_b_id, card_b_name, rps_description,
                             damage_to_a, damage_to_b, hp_a_after, hp_b_after,
                             special_events, winner_side,
                             state_a_snapshot, state_b_snapshot,
                             resource_logs_a, resource_logs_b, created_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7,
                                $8, $9, $10, $11,
                                $12::text[], $13,
                                $14::jsonb, $15::jsonb,
                                '{}'::text[], '{}'::text[], $16)
                        """,
                        battle_id,
                        round_number,
                        card_a_id,
                        card_a_name,
                        card_b_id,
                        card_b_name,
                        rps_description,
                        damage_to_a,
                        damage_to_b,
                        hp_a_after,
                        hp_b_after,
                        special_events if special_events else [],
                        winner,
                        json.dumps(state_a, ensure_ascii=False) if state_a else None,
                        json.dumps(state_b, ensure_ascii=False) if state_b else None,
                        now,
                    )

                    # 2. 更新双方战斗状态
                    if state_a:
                        await self._update_player_state(
                            conn, battle_id, "A", state_a, now
                        )
                    if state_b:
                        await self._update_player_state(
                            conn, battle_id, "B", state_b, now
                        )

                    # 3. 更新对战表
                    if battle_ended:
                        await conn.execute(
                            """
                            UPDATE battles
                            SET state = '已结束',
                                winner = $2,
                                current_round = $3,
                                updated_at = $4
                            WHERE battle_id = $1
                            """,
                            battle_id,
                            winner or "draw",
                            round_number,
                            now,
                        )
                    else:
                        await conn.execute(
                            """
                            UPDATE battles
                            SET current_round = $2, updated_at = $3
                            WHERE battle_id = $1
                            """,
                            battle_id,
                            round_number,
                            now,
                        )

            logger.info(
                f"PG sync: round {round_number} resolved "
                f"battle={battle_id} ended={battle_ended}"
            )
        except Exception as e:
            logger.error(
                f"PG sync failed (round): battle={battle_id} "
                f"round={round_number} error={e}"
            )
            raise

    async def _update_player_state(
        self,
        conn: asyncpg.Connection,
        battle_id: str,
        side: str,
        resources: Dict[str, int],
        now: datetime,
    ):
        """更新单个玩家的战斗状态字段"""
        await conn.execute(
            """
            UPDATE battle_players
            SET hp = $3,
                edge = $4,
                phantom = $5,
                charge = $6,
                chill = $7,
                pulse = $8,
                read = $9,
                insight = $10,
                submitted = FALSE,
                updated_at = $11
            WHERE battle_id = $1 AND side = $2
            """,
            battle_id,
            side,
            resources.get("hp", 0),
            resources.get("edge", 0),
            resources.get("phantom", 0),
            resources.get("charge", 0),
            resources.get("chill", 0),
            resources.get("pulse", 0),
            resources.get("read", 0),
            resources.get("insight", 0),
            now,
        )

    # ════════════════════════════════════════════════════
    # sync_deck_confirmed
    # ════════════════════════════════════════════════════

    async def sync_deck_confirmed(
        self,
        battle_id: str,
        side: str,
        deck: List[str],
    ):
        """牌库确认 — 写入 deck_slots JSONB"""
        if not self.enabled:
            return

        now = datetime.now(timezone.utc)
        try:
            result = await self._pool.execute(
                """
                UPDATE battle_players
                SET deck_slots = $3::jsonb,
                    deck_confirmed = TRUE,
                    updated_at = $4
                WHERE battle_id = $1 AND side = $2
                """,
                battle_id,
                side,
                json.dumps(deck, ensure_ascii=False),
                now,
            )
            if result == "UPDATE 0":
                logger.warning(
                    f"PG sync: deck_confirmed — no row for "
                    f"{battle_id}/{side}"
                )
            else:
                logger.info(
                    f"PG sync: {side} deck confirmed in {battle_id}"
                )
        except Exception as e:
            logger.error(
                f"PG sync failed (deck_confirm): "
                f"battle={battle_id} side={side} error={e}"
            )
            raise

    # ════════════════════════════════════════════════════
    # check_both_decks_confirmed
    # ════════════════════════════════════════════════════

    async def check_both_decks_confirmed(self, battle_id: str) -> bool:
        """检查双方是否都已确认牌库"""
        if not self.enabled:
            return True

        try:
            rows = await self._pool.fetch(
                """
                SELECT side, deck_confirmed
                FROM battle_players
                WHERE battle_id = $1
                ORDER BY side
                """,
                battle_id,
            )
            if len(rows) < 2:
                return False
            return all(r["deck_confirmed"] for r in rows)
        except Exception as e:
            logger.error(
                f"PG sync failed (check_decks): "
                f"battle={battle_id} error={e}"
            )
            return False

    # ════════════════════════════════════════════════════
    # clear_submission_flags（兼容接口，内部使用）
    # ════════════════════════════════════════════════════

    async def clear_submission_flags(self, battle_id: str):
        """清除双方已提交标记"""
        if not self.enabled:
            return

        now = datetime.now(timezone.utc)
        try:
            await self._pool.execute(
                """
                UPDATE battle_players
                SET submitted = FALSE, updated_at = $2
                WHERE battle_id = $1
                """,
                battle_id,
                now,
            )
        except Exception as e:
            logger.error(
                f"PG sync failed (clear_flags): "
                f"battle={battle_id} error={e}"
            )
            raise
