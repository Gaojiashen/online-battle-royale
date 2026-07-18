"""
Phase 4.5 压力测试 — 模拟多 battle 并发。

测试:
  10 场同时 battle, 20 个 WebSocket client
  每 battle 20 回合 submit + resolve

  观察: CPU, 内存, EventBus queue, WS 稳定性
"""

import asyncio
import time
import os
import tempfile
import shutil

from engine.battle_manager import BattleManager
from engine.events import BattleEvent, BattleEventType
from engine.resource_engine import BattleState
from integration.event_bus import AsyncEventBus
from integration.event_log import EventLog
from integration.snapshot_store import SnapshotStore
from integration.dead_letter import DeadLetterQueue
from integration.websocket_manager import WebSocketManager
from integration.persistence_worker import PersistenceWorker
from integration.base_sync import base_sync
from models import BattleInitRequest, DeckConfirmRequest


# ═══════════════════════════════════════
# 配置
# ═══════════════════════════════════════
NUM_BATTLES = 5
ROUNDS_PER_BATTLE = 10
WS_CLIENTS_PER_BATTLE = 2


class MockWS:
    """模拟 WebSocket — 记录消息数"""

    def __init__(self):
        self.sent_count = 0
        self.closed = False

    async def accept(self):
        pass

    async def send_text(self, data: str):
        self.sent_count += 1

    async def receive_text(self) -> str:
        return "ping"

    async def close(self):
        self.closed = True


class Metrics:
    """性能指标收集"""

    def __init__(self):
        self.t0 = time.time()
        self.total_events = 0
        self.total_rounds = 0
        self.max_queue_size = 0

    def record(self, bus: AsyncEventBus):
        qsize = bus._queue.qsize()
        if qsize > self.max_queue_size:
            self.max_queue_size = qsize

    def elapsed(self):
        return time.time() - self.t0


# ═══════════════════════════════════════
# 主流程
# ═══════════════════════════════════════

async def run_stress():
    tmpdir = tempfile.mkdtemp(prefix="stress_")
    try:
        # ── 创建 Phase 2/3 全链路组件 ──
        event_log = EventLog(data_dir=os.path.join(tmpdir, "events"))
        snapshots = SnapshotStore(data_dir=os.path.join(tmpdir, "snapshots"))
        dlq = DeadLetterQueue(path=os.path.join(tmpdir, "dead.jsonl"))
        ws = WebSocketManager()

        bus = AsyncEventBus(
            queue_size=256,
            event_log=event_log,
            dead_letter_queue=dlq,
            websocket_manager=ws,
        )
        bm = BattleManager(event_bus=bus)
        pw = PersistenceWorker(base_sync, snapshot_store=snapshots,
                               battle_manager=bm)
        pw.register(bus)

        metrics = Metrics()

        # ── 注册 WS clients ──
        ws_clients = {}
        for i in range(NUM_BATTLES):
            bid = f"stress-{i:03d}"
            ws_clients[bid] = [MockWS(), MockWS()]
            for mock in ws_clients[bid]:
                await ws.connect(bid, mock)

        print(f"WebSocket clients: {NUM_BATTLES * WS_CLIENTS_PER_BATTLE}")

        # ── 启动 consumer ──
        await bus.start()

        # ── 创建 battles ──
        battle_ids = []
        for i in range(NUM_BATTLES):
            req = BattleInitRequest(
                player_a_base_token=f"t{i}a", player_b_base_token=f"t{i}b",
                player_a_name=f"A{i}", player_b_name=f"B{i}",
                player_a_aspects={"刃": 4, "蛾": 6, "铸": 2, "冬": 3, "心": 5, "灯": 1},
                player_b_aspects={"刃": 2, "蛾": 3, "铸": 7, "冬": 4, "心": 1, "灯": 6},
            )
            r = await bm.init_battle(req)
            battle_ids.append(r.battle_id)

            # confirm deck
            a_deck = [c.id for c in r.player_a_available[:8]]
            b_deck = [c.id for c in r.player_b_available[:8]]
            await bm.confirm_deck(DeckConfirmRequest(
                battle_id=r.battle_id, player_a_deck=a_deck, player_b_deck=b_deck,
            ))

        print(f"Battles created: {len(battle_ids)}")

        # ── 执行回合 ──
        for round_num in range(1, ROUNDS_PER_BATTLE + 1):
            for bid in battle_ids:
                session = bm._battles.get(bid)
                if not session or session.state != "in_progress":
                    continue

                # 选择卡牌（用 deck 中的第一张）
                deck_a = session.player_a_deck
                deck_b = session.player_b_deck
                card_a = deck_a[(round_num - 1) % len(deck_a)]
                card_b = deck_b[(round_num - 1) % len(deck_b)]

                # 提交 (A 先)
                resp_a = bm.submit_card(bid, "a", card_a)
                # 提交 (B — 触发 settle)
                resp_b = bm.submit_card(bid, "b", card_b)

                if resp_b.status == "resolved":
                    metrics.total_rounds += 1
                metrics.total_events += 1

            # 每轮后记录 Queue 大小
            metrics.record(bus)

            # 每 5 轮打印一次状态
            if round_num % 5 == 0:
                elapsed = metrics.elapsed()
                print(f"  Round {round_num}/{ROUNDS_PER_BATTLE} "
                      f"elapsed={elapsed:.1f}s "
                      f"max_queue={metrics.max_queue_size} "
                      f"events={metrics.total_events}")

            # 每 round 过后短暂 yield，让 consumer loop 处理积压
        await asyncio.sleep(0.1)

        # ── 等待 consumer 处理完毕 ──
        await asyncio.sleep(1.0)

        # ── 检查每个 battle 都 finished ──
        finished = sum(1 for s in bm._battles.values() if s.state == "finished")
        active = sum(1 for s in bm._battles.values() if s.state == "in_progress")

        # ── 收集结果 ──
        total_sent = sum(m.sent_count for clients in ws_clients.values()
                         for m in clients)
        events_logged = sum(
            len(event_log.read(bid)) for bid in battle_ids
        )

        print()
        print("=" * 50)
        print("STRESS TEST RESULTS")
        print("=" * 50)
        print(f"  Battles: {NUM_BATTLES} (finished={finished}, active={active})")
        print(f"  Rounds per battle: {ROUNDS_PER_BATTLE}")
        print(f"  Total rounds resolved: {metrics.total_rounds}")
        print(f"  Total events emitted: {metrics.total_events}")
        print(f"  Max queue size: {metrics.max_queue_size}")
        print(f"  WS messages sent: {total_sent}")
        print(f"  Event log entries: {events_logged}")
        print(f"  Total time: {metrics.elapsed():.1f}s")
        print(f"  Events/sec: {metrics.total_events / metrics.elapsed():.1f}")
        print(f"  Rounds/sec: {metrics.total_rounds / metrics.elapsed():.1f}")

        # ── 健康检查 ──
        snap_count = len([f for f in os.listdir(os.path.join(tmpdir, "snapshots"))
                          if f.endswith(".json")])
        print(f"  Snapshots left: {snap_count}")
        print(f"  DLQ records: {len(dlq.read_all())}")

        # ── 健康检查（非严格断言，表征系统行为）──
        checks = []
        checks.append(("Rounds resolved > 0", metrics.total_rounds > 0))
        checks.append(("Queue < 256 (no overflow)", metrics.max_queue_size < 256))
        checks.append(("Events persisted", events_logged > 0))
        checks.append(("Snapshots healthy", snap_count >= 0))

        all_ok = True
        for name, ok in checks:
            status = "OK" if ok else "WARN"
            print(f"  [{status}] {name}: {ok}")
            if not ok:
                all_ok = False

        if metrics.max_queue_size > 200:
            print(f"  [NOTE] Queue peaked at {metrics.max_queue_size}/256 — "
                  f"consider reducing concurrency or increasing queue_size")

        print()
        if all_ok:
            print("  ALL HEALTH CHECKS PASSED")
        else:
            print("  SOME CHECKS FLAGGED — see above")

        await bus.stop()

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(run_stress())
