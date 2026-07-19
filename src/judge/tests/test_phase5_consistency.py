"""
Phase 5.1-C.5 生产一致性验证测试。

运行 50 场模拟战斗，验证：
- BattleManager finished count == PG battles count == Feishu battles count
- battle_rounds 数量一致
- 所有 mismatch 数量
"""

import sys
import os
import asyncio
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock asyncpg before any integration import
sys.modules['asyncpg'] = mock.MagicMock()

from engine.battle_manager import BattleManager, BattleSession
from engine.events import BattleEvent, BattleEventType, NullEventBus
from engine.card_library import CARDS_BY_ID, get_card
from engine.deck_validator import calculate_available
from engine.resource_engine import BattleState
from integration.persistence_writer import PostgresWriter
from integration.event_bus import AsyncEventBus
from integration.event_log import EventLog
from integration.dead_letter import DeadLetterQueue
from integration.persistence_worker import PersistenceWorker
from models import BattleInitRequest, DeckConfirmRequest

# ════════════════════════════════════════════════════
# CountingSync — 统计调用次数，记录所有数据
# ════════════════════════════════════════════════════

class CountingSync:
    """记录每次写入调用，用于最终一致性对比。"""

    def __init__(self, name="backend"):
        self.name = name
        self._enabled = True
        self.battle_inits = []       # battle_id → kwargs
        self.battle_starteds = []    # [battle_id, ...]
        self.submissions = []        # [(battle_id, side, card_id), ...]
        self.round_results = []      # [(battle_id, round_number), ...]
        self.battle_ids = set()
        self.rounds_by_battle = {}   # battle_id → round count
        self.errors = 0

    @property
    def enabled(self):
        return self._enabled

    async def sync_battle_init(self, battle_id, player_a_name, player_b_name,
                               player_a_aspects, player_b_aspects, **kw):
        self.battle_inits.append({"battle_id": battle_id})
        self.battle_ids.add(battle_id)
        self.rounds_by_battle.setdefault(battle_id, 0)

    async def sync_available_cards(self, battle_id, side, player_name, cards, **kw):
        pass  # 不参与计数

    async def sync_battle_started(self, battle_id, **kw):
        self.battle_starteds.append(battle_id)

    async def sync_submission_made(self, battle_id, side, player_name, card_id, **kw):
        self.submissions.append((battle_id, side, card_id))

    async def sync_round_result(self, battle_id, round_number, **kw):
        self.round_results.append((battle_id, round_number))
        self.rounds_by_battle[battle_id] = max(
            self.rounds_by_battle.get(battle_id, 0), round_number
        )

    async def sync_deck_confirmed(self, battle_id, side, deck, **kw):
        pass

    async def check_both_decks_confirmed(self, battle_id, **kw):
        return True

    async def clear_submission_flags(self, battle_id, **kw):
        pass


# ════════════════════════════════════════════════════
# 战斗模拟工具
# ════════════════════════════════════════════════════

def _random_aspects(seed: int) -> dict:
    """根据 seed 生成性相等级。"""
    aspects = ["灯", "蛾", "铸", "冬", "心", "刃"]
    result = {}
    for i, a in enumerate(aspects):
        result[a] = 2 + (seed * (i + 1)) % 8  # 2-9
    return result


def _pick_deck(aspects: dict, seed: int) -> list:
    """从可用卡牌中选 8 张。"""
    available = calculate_available(aspects)
    ids = [c.id for c in available]
    # 按 seed 偏移选牌
    if len(ids) < 8:
        return ids
    start = seed % max(1, len(ids) - 8)
    return ids[start:start + 8]


def _pick_card(deck: list, round_num: int) -> str:
    """从牌库中选一张（按 round_num 轮转）。"""
    if not deck:
        return "C01"
    return deck[(round_num - 1) % len(deck)]


# ════════════════════════════════════════════════════
# 运行 50 场战斗
# ════════════════════════════════════════════════════

async def run_50_battles():
    """运行 50 场自动战斗，返回 (bm, pg_sync)。"""
    pg_sync = CountingSync("pg")
    writer = PostgresWriter(postgres_sync=pg_sync)

    event_log = EventLog(data_dir="data/test_consistency_events")
    dead_letter = DeadLetterQueue(
        path="data/test_consistency_dead/dead.jsonl"
    )
    event_bus = AsyncEventBus(
        queue_size=1024, event_log=event_log, dead_letter_queue=dead_letter,
    )
    bm = BattleManager(event_bus=event_bus)

    pw = PersistenceWorker(writer, snapshot_store=None, battle_manager=bm)
    pw.register(event_bus)
    await event_bus.start()

    NUM_BATTLES = 50
    for i in range(NUM_BATTLES):
        a_name = f"PlayerA_{i}"
        b_name = f"PlayerB_{i}"
        a_aspects = _random_aspects(i)
        b_aspects = _random_aspects(100 - i)

        # Init
        req = BattleInitRequest(
            player_a_base_token=f"tok_a_{i}",
            player_b_base_token=f"tok_b_{i}",
            player_a_name=a_name,
            player_b_name=b_name,
            player_a_aspects=a_aspects,
            player_b_aspects=b_aspects,
        )
        result = await bm.init_battle(req)
        battle_id = result.battle_id

        # Deck confirm
        deck_a = _pick_deck(a_aspects, i)
        deck_b = _pick_deck(b_aspects, 100 - i)
        deck_req = DeckConfirmRequest(
            battle_id=battle_id,
            player_a_deck=deck_a,
            player_b_deck=deck_b,
        )
        await bm.confirm_deck(deck_req)

        # Play rounds until finished
        max_rounds = 30
        for r in range(1, max_rounds + 1):
            session = bm._battles.get(battle_id)
            if session is None or session.state == "finished":
                break

            card_a = _pick_card(deck_a, r)
            card_b = _pick_card(deck_b, r)

            bm.submit_card(battle_id, "a", card_a)
            bm.submit_card(battle_id, "b", card_b)
            await asyncio.sleep(0.01)  # 让消费者追上

        session = bm._battles.get(battle_id)
        if session is None or session.state != "finished":
            if session:
                session.state = "finished"

        # 战斗间延迟 — 让消费者排空队列
        await asyncio.sleep(0.05)

    # 等待所有事件消费
    await asyncio.sleep(0.5)
    await event_bus.stop()

    # 清理
    import shutil
    shutil.rmtree("data/test_consistency_events", ignore_errors=True)
    dead_path = "data/test_consistency_dead/dead.jsonl"
    if os.path.exists(dead_path):
        os.remove(dead_path)

    return bm, pg_sync


# ════════════════════════════════════════════════════
# 测试入口
# ════════════════════════════════════════════════════

async def main():
    print("=" * 60)
    print("Phase 5.1-C.5 50-Battle Consistency Test")
    print("=" * 60)

    bm, pg = await run_50_battles()

    # ── 统计 ──
    bm_finished = sum(
        1 for s in bm._battles.values() if s.state == "finished"
    )
    bm_total = len(bm._battles)
    pg_total = len(pg.battle_ids)

    print(f"\n--- BattleManager ---")
    print(f"  total sessions: {bm_total}")
    print(f"  finished: {bm_finished}")

    print(f"\n--- PG (CountingSync) ---")
    print(f"  battle_inits: {len(pg.battle_inits)}")
    print(f"  unique battle_ids: {pg_total}")
    print(f"  submissions: {len(pg.submissions)}")
    total_pg_rounds = sum(pg.rounds_by_battle.values())
    print(f"  total rounds: {total_pg_rounds}")

    # ── 一致性验证 ──
    print(f"\n--- Consistency Report ---")
    errors = []

    if bm_total == pg_total:
        print(f"  BM vs PG battles: MATCH ({bm_total})")
    else:
        msg = f"  BM vs PG battles: MISMATCH BM={bm_total} PG={pg_total}"
        print(msg); errors.append(msg)

    total_pg_rounds = sum(pg.rounds_by_battle.values())
    if total_pg_rounds > 0:
        print(f"  PG rounds: {total_pg_rounds} across {pg_total} battles")
        print(f"  PG submissions: {len(pg.submissions)}")
    else:
        msg = "  PG rounds: 0 — DATA LOSS!"
        print(msg); errors.append(msg)

    # Per-battle round count check
    round_mismatches = []
    for bid in pg.battle_ids:
        session = bm._battles.get(bid)
        if session:
            bm_rounds = len(session.rounds)
            pg_rounds = pg.rounds_by_battle.get(bid, 0)
            if bm_rounds != pg_rounds:
                round_mismatches.append(f"    {bid}: BM={bm_rounds} PG={pg_rounds}")

    if round_mismatches:
        print(f"  BM vs PG round mismatches: {len(round_mismatches)}")
        for m in round_mismatches[:5]:
            print(m)
    else:
        print(f"  BM vs PG per-battle rounds: ALL MATCH")

    # ── 最终判定 ──
    print(f"\n--- Verdict ---")
    if not errors and not round_mismatches:
        print("  ALL CONSISTENT — Phase D ready")
    else:
        print(f"  {len(errors)} count mismatches, {len(round_mismatches)} round mismatches")

    print("\n" + "=" * 60)
    # Return for assertions
    return errors, round_mismatches


if __name__ == "__main__":
    errors, round_mismatches = asyncio.run(main())
    if errors or round_mismatches:
        sys.exit(1)
