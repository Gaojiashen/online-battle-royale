"""
Phase 2 集成测试 — 端到端验证全链路。

覆盖:
  Case 1: 完整战斗流程 → event log 生成
  Case 2: ROUND_RESOLVED → snapshot 生成
  Case 3: 模拟重启 → recover_all_sessions
  Case 4: handler 永久失败 → DLQ 记录
"""

import os
import json
import tempfile
import shutil
import asyncio
import time
import logging

logging.basicConfig(level=logging.WARNING)

from engine.battle_manager import BattleManager
from engine.events import BattleEvent, BattleEventType, NullEventBus
from engine.deck_validator import calculate_available
from engine.card_library import CARDS_BY_ID
from integration.event_bus import AsyncEventBus
from integration.event_log import EventLog
from integration.snapshot_store import SnapshotStore
from integration.dead_letter import DeadLetterQueue
from integration.persistence_worker import PersistenceWorker
from integration.recovery import RecoveryManager
from integration.base_sync import base_sync
from models import BattleInitRequest, DeckConfirmRequest


# ════════════════════════════════════════════════════
# 辅助
# ════════════════════════════════════════════════════

def make_battle_request():
    return BattleInitRequest(
        player_a_base_token="t1", player_b_base_token="t2",
        player_a_name="Alice", player_b_name="Bob",
        player_a_aspects={"刃": 4, "蛾": 6, "铸": 2, "冬": 3, "心": 5, "灯": 1},
        player_b_aspects={"刃": 2, "蛾": 3, "铸": 7, "冬": 4, "心": 1, "灯": 6},
    )


# ════════════════════════════════════════════════════
# Case 1: 完整流程 → event log
# ════════════════════════════════════════════════════

def test_full_flow_event_log():
    tmpdir = tempfile.mkdtemp(prefix="p2_int_")
    try:
        event_log = EventLog(data_dir=os.path.join(tmpdir, "events"))
        snapshots = SnapshotStore(data_dir=os.path.join(tmpdir, "snapshots"))
        dlq = DeadLetterQueue(path=os.path.join(tmpdir, "dead.jsonl"))
        bus = AsyncEventBus(queue_size=32, event_log=event_log,
                            dead_letter_queue=dlq)
        bm = BattleManager(event_bus=bus)
        pw = PersistenceWorker(base_sync, snapshot_store=snapshots,
                               battle_manager=bm)
        pw.register(bus)

        async def run():
            await bus.start()

            # init
            req = make_battle_request()
            r = await bm.init_battle(req)
            bid = r.battle_id

            # confirm
            a_deck = [c.id for c in r.player_a_available[:8]]
            b_deck = [c.id for c in r.player_b_available[:8]]
            dr = DeckConfirmRequest(battle_id=bid, player_a_deck=a_deck,
                                    player_b_deck=b_deck)
            r2 = await bm.confirm_deck(dr)

            # submit both sides → trigger resolve
            bm.submit_card(bid, "a", a_deck[0])
            bm.submit_card(bid, "b", b_deck[0])

            await asyncio.sleep(0.5)
            await bus.stop()

            # 验证 event log
            events = event_log.read(bid)
            print(f"  Event log entries: {len(events)}")
            types = [e.type.value for e in events]
            print(f"  Event types: {types}")
            assert len(events) >= 3  # BATTLE_CREATED + DECK_CONFIRMED + ROUND_RESOLVED
            assert "battle_created" in types
            assert "deck_confirmed" in types
            assert "round_resolved" in types
            # CARD_SUBMITTED events depend on whether handler processed before bus.stop

        asyncio.run(run())
        print("  PASS: event log generated")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# Case 2: Snapshot 生成
# ════════════════════════════════════════════════════

def test_snapshot_generation():
    tmpdir = tempfile.mkdtemp(prefix="p2_snap_")
    try:
        event_log = EventLog(data_dir=os.path.join(tmpdir, "events"))
        snapshots = SnapshotStore(data_dir=os.path.join(tmpdir, "snapshots"))
        dlq = DeadLetterQueue(path=os.path.join(tmpdir, "dead.jsonl"))
        bus = AsyncEventBus(queue_size=32, event_log=event_log,
                            dead_letter_queue=dlq)
        bm = BattleManager(event_bus=bus)
        pw = PersistenceWorker(base_sync, snapshot_store=snapshots,
                               battle_manager=bm)
        pw.register(bus)

        async def run():
            await bus.start()
            req = make_battle_request()
            r = await bm.init_battle(req)
            bid = r.battle_id

            a_deck = [c.id for c in r.player_a_available[:8]]
            b_deck = [c.id for c in r.player_b_available[:8]]
            dr = DeckConfirmRequest(battle_id=bid, player_a_deck=a_deck,
                                    player_b_deck=b_deck)
            await bm.confirm_deck(dr)

            # 打 3 回合 (round 3 % 3 == 0 → snapshot)
            for round_num in range(1, 4):
                bm.submit_card(bid, "a", a_deck[round_num % len(a_deck)])
                bm.submit_card(bid, "b", b_deck[round_num % len(b_deck)])
                await asyncio.sleep(0.05)

            await asyncio.sleep(1.0)  # let handlers complete
            await bus.stop()

            # 验证 snapshot
            snap = snapshots.load(bid)
            assert snap is not None, "Snapshot should exist"
            print(f"  Snapshot round: {snap['current_round']}")
            print(f"  Snapshot state: {snap['battle_state']}")
            print(f"  Snapshot HP-A: {snap['state_a']['hp']}")
            print(f"  Snapshot HP-B: {snap['state_b']['hp']}")
            assert snap["battle_state"] == "in_progress"
            assert snap["current_round"] >= 3

        asyncio.run(run())
        print("  PASS: snapshot generated")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# Case 3: 模拟重启 → 恢复
# ════════════════════════════════════════════════════

def test_restart_recovery():
    tmpdir = tempfile.mkdtemp(prefix="p2_recover_")
    try:
        events_dir = os.path.join(tmpdir, "events")
        snaps_dir = os.path.join(tmpdir, "snapshots")
        dlq_path = os.path.join(tmpdir, "dead.jsonl")

        event_log = EventLog(data_dir=events_dir)
        snapshots = SnapshotStore(data_dir=snaps_dir)
        dlq = DeadLetterQueue(path=dlq_path)
        bus = AsyncEventBus(queue_size=32, event_log=event_log,
                            dead_letter_queue=dlq)
        bm = BattleManager(event_bus=bus)
        pw = PersistenceWorker(base_sync, snapshot_store=snapshots,
                               battle_manager=bm)
        pw.register(bus)

        async def before_crash():
            await bus.start()
            req = make_battle_request()
            r = await bm.init_battle(req)
            bid = r.battle_id

            a_deck = [c.id for c in r.player_a_available[:8]]
            b_deck = [c.id for c in r.player_b_available[:8]]
            await bm.confirm_deck(DeckConfirmRequest(
                battle_id=bid, player_a_deck=a_deck, player_b_deck=b_deck))

            # 打 1 回合
            bm.submit_card(bid, "a", a_deck[0])
            bm.submit_card(bid, "b", b_deck[0])
            await asyncio.sleep(1.0)  # let handler save snapshot

            # 记录崩溃前状态
            session = bm._battles[bid]
            pre_crash = {
                "battle_id": bid,
                "state": session.state,
                "current_round": session.current_round,
                "hp_a": session.state_a.hp,
                "hp_b": session.state_b.hp,
                "edge_a": session.state_a.edge,
                "edge_b": session.state_b.edge,
            }
            await bus.stop()
            return pre_crash

        pre = asyncio.run(before_crash())
        bid = pre["battle_id"]
        print(f"  Pre-crash: state={pre['state']} r={pre['current_round']} "
              f"HP-A={pre['hp_a']} HP-B={pre['hp_b']}")

        # 验证 snapshot 存在
        snap = snapshots.load(bid)
        assert snap is not None

        # 模拟重启：新 BM + RecoveryManager
        event_log2 = EventLog(data_dir=events_dir)
        snapshots2 = SnapshotStore(data_dir=snaps_dir)
        bm2 = BattleManager()
        recovery = RecoveryManager(bm2, snapshots2, event_log2)
        count = recovery.recover_all_sessions()
        assert count == 1

        restored = bm2._battles[bid]
        assert restored is not None
        assert restored.state == pre["state"]
        assert restored.current_round == pre["current_round"]
        assert restored.state_a.hp == pre["hp_a"]
        assert restored.state_b.hp == pre["hp_b"]
        print(f"  Post-recovery: state={restored.state} r={restored.current_round} "
              f"HP-A={restored.state_a.hp} HP-B={restored.state_b.hp}")

        print("  PASS: restart recovery")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# Case 4: handler 永久失败 → DLQ
# ════════════════════════════════════════════════════

def test_dlq_integration():
    tmpdir = tempfile.mkdtemp(prefix="p2_dlq_")
    try:
        dlq_path = os.path.join(tmpdir, "dead.jsonl")
        dlq = DeadLetterQueue(path=dlq_path)
        bus = AsyncEventBus(queue_size=32, dead_letter_queue=dlq)

        class BrokenHandler:
            def __init__(self):
                self.calls = 0
            async def handle(self, event):
                self.calls += 1
                raise RuntimeError("broken")

        h = BrokenHandler()
        bus.subscribe(BattleEventType.CARD_SUBMITTED, h.handle)

        async def run():
            await bus.start()
            ev = BattleEvent.create(BattleEventType.CARD_SUBMITTED, "dlq-battle",
                                     {"side": "a"}, max_retries=2)
            bus.emit(ev)
            await asyncio.sleep(5.0)
            await bus.stop()

            records = dlq.read_all()
            print(f"  DLQ records: {len(records)}")
            for r in records:
                print(f"    event_id={r['event_id'][:8]}... battle={r['battle_id']} "
                      f"retry={r['retry_count']}")
            assert len(records) >= 1
            assert records[0]["battle_id"] == "dlq-battle"
            assert records[0]["retry_count"] >= 2

        asyncio.run(run())
        print("  PASS: DLQ integration")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# 运行
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2 Integration Tests")
    print("=" * 60)

    test_full_flow_event_log()
    test_snapshot_generation()
    test_restart_recovery()
    test_dlq_integration()

    print()
    print("Results: 4 passed, 0 failed, 4 total")
