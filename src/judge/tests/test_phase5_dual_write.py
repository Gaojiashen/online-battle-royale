"""
Phase 5.1 PostgresWriter PG-only 测试。

验证 PersistenceWorker → PostgresWriter → PostgresSync 调用链。
"""

import sys
import os
import asyncio
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.modules['asyncpg'] = mock.MagicMock()

from integration.persistence_writer import PostgresWriter
from integration.event_bus import AsyncEventBus
from integration.event_log import EventLog
from integration.dead_letter import DeadLetterQueue
from integration.persistence_worker import PersistenceWorker
from engine.battle_manager import BattleManager
from engine.events import BattleEvent, BattleEventType
from integration.snapshot_store import SnapshotStore


class PGSpy:
    """PostgresSync spy，记录调用并验证 PG 是唯一写入目标。"""

    def __init__(self, name="pg", fail_on=None):
        self.name = name
        self._enabled = True
        self._fail_on = fail_on or set()
        self.calls = []
        self.error_count = 0

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, v):
        self._enabled = v

    def _record(self, method, kwargs):
        self.calls.append((method, kwargs))
        if method in self._fail_on:
            self.error_count += 1
            raise RuntimeError(f"{self.name}: forced failure in {method}")

    async def sync_battle_init(self, **kw):
        self._record("sync_battle_init", kw)
    async def sync_available_cards(self, **kw):
        self._record("sync_available_cards", kw)
    async def sync_battle_started(self, **kw):
        self._record("sync_battle_started", kw)
    async def sync_submission_made(self, **kw):
        self._record("sync_submission_made", kw)
    async def sync_round_result(self, **kw):
        self._record("sync_round_result", kw)
    async def sync_deck_confirmed(self, **kw):
        self._record("sync_deck_confirmed", kw)
    async def check_both_decks_confirmed(self, battle_id):
        self._record("check_both_decks_confirmed", {"battle_id": battle_id})
        return True
    async def clear_submission_flags(self, **kw):
        self._record("clear_submission_flags", kw)


# ════════════════════════════════════════════════════
# Test 1: PG write
# ════════════════════════════════════════════════════

async def test_pg_write():
    pg = PGSpy("pg")
    dw = PostgresWriter(postgres_sync=pg)

    await dw.sync_battle_init(
        battle_id="t1", player_a_name="A", player_b_name="B",
        player_a_aspects={}, player_b_aspects={},
    )
    await dw.sync_battle_started(battle_id="t1")
    await dw.sync_submission_made(battle_id="t1", side="A", player_name="A", card_id="C01")
    await dw.sync_round_result(
        battle_id="t1", round_number=1,
        card_a_name="C01 X", card_b_name="C02 Y",
        rps_description="test", damage_to_a=0, damage_to_b=0,
        hp_a_after=20, hp_b_after=20,
        special_events=[], winner=None, battle_ended=False,
    )
    await dw.sync_deck_confirmed(battle_id="t1", side="A", deck=["C01"]*8)

    methods = [c[0] for c in pg.calls]
    assert "sync_battle_init" in methods
    assert "sync_battle_started" in methods
    assert "sync_submission_made" in methods
    assert "sync_round_result" in methods
    assert "sync_deck_confirmed" in methods
    print("  [PASS] test_pg_write: all 5 methods called")


# ════════════════════════════════════════════════════
# Test 2: check_decks
# ════════════════════════════════════════════════════

async def test_check_decks():
    pg = PGSpy("pg")
    dw = PostgresWriter(postgres_sync=pg)
    result = await dw.check_both_decks_confirmed("t2")
    assert result is True
    assert ("check_both_decks_confirmed" in [c[0] for c in pg.calls])
    print("  [PASS] test_check_decks: calls PG")


# ════════════════════════════════════════════════════
# Test 3: enabled
# ════════════════════════════════════════════════════

async def test_enabled():
    pg = PGSpy("pg")
    dw = PostgresWriter(postgres_sync=pg)
    assert dw.enabled is True
    pg.enabled = False
    assert dw.enabled is False
    print("  [PASS] test_enabled: reflects PG state")


# ════════════════════════════════════════════════════
# Test 4: PG failure doesn't crash
# ════════════════════════════════════════════════════

async def test_pg_failure_no_crash():
    pg = PGSpy("pg", fail_on={"sync_battle_started"})
    dw = PostgresWriter(postgres_sync=pg)
    await dw.sync_battle_started(battle_id="t4")
    assert pg.error_count == 1
    print("  [PASS] test_pg_failure_no_crash: logged but not raised")


# ════════════════════════════════════════════════════
# Test 5: PersistenceWorker integration
# ════════════════════════════════════════════════════

async def test_persistence_worker_integration():
    pg = PGSpy("pg")
    dw = PostgresWriter(postgres_sync=pg)
    event_log = EventLog(data_dir="data/test_pw_events")
    dead_letter = DeadLetterQueue(path="data/test_pw_dead/dead.jsonl")
    event_bus = AsyncEventBus(queue_size=64, event_log=event_log, dead_letter_queue=dead_letter)
    bm = BattleManager(event_bus=event_bus)
    snapshots = SnapshotStore(data_dir="data/test_pw_snapshots")
    pw = PersistenceWorker(dw, snapshot_store=snapshots, battle_manager=bm)
    pw.register(event_bus)
    await event_bus.start()

    event = BattleEvent.create(BattleEventType.BATTLE_CREATED, battle_id="t5", data={
        "player_a_name": "A", "player_b_name": "B",
        "player_a_aspects": {}, "player_b_aspects": {},
        "player_a_available": [], "player_b_available": [],
    })
    event_bus.emit(event)
    await asyncio.sleep(0.2)
    await event_bus.stop()

    init_calls = [c for c in pg.calls if c[0] == "sync_battle_init"]
    assert len(init_calls) == 1
    assert init_calls[0][1]["battle_id"] == "t5"

    import shutil
    shutil.rmtree("data/test_pw_events", ignore_errors=True)
    shutil.rmtree("data/test_pw_snapshots", ignore_errors=True)
    dl = "data/test_pw_dead/dead.jsonl"
    if os.path.exists(dl): os.remove(dl)
    print("  [PASS] test_persistence_worker_integration: event → PW → PG")


async def main():
    print("=" * 60)
    print("Phase 5.1 PostgresWriter PG-only Test")
    print("=" * 60)
    await test_pg_write()
    await test_check_decks()
    await test_enabled()
    await test_pg_failure_no_crash()
    await test_persistence_worker_integration()
    print("\n" + "=" * 60)
    print("5 tests passed [OK]")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
