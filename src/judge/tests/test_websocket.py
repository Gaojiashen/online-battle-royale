"""
WebSocket 集成测试。

覆盖:
  Case 1: WebSocketManager connect + broadcast → 收到消息
  Case 2: 两个客户端连接同 battle → 两个都收到
  Case 3: 断连不影响其他客户端
  Case 4: WebSocket 推送失败不影响 PersistenceWorker
  Case 5: EventBus 集成 — emit 触发 broadcast
  Case 6: 消息格式正确
"""

import json
import asyncio
import logging

logging.basicConfig(level=logging.WARNING)

from engine.events import BattleEvent, BattleEventType
from integration.websocket_manager import WebSocketManager
from integration.event_bus import AsyncEventBus


# ════════════════════════════════════════════════════
# Mock WebSocket
# ════════════════════════════════════════════════════

class MockWebSocket:
    """模拟 WebSocket — 记录发送的消息"""

    def __init__(self, fail_on_send: bool = False):
        self.sent: list = []
        self.accepted: bool = False
        self.closed: bool = False
        self._fail = fail_on_send

    async def accept(self):
        self.accepted = True

    async def send_text(self, data: str):
        if self._fail:
            raise ConnectionError("simulated send failure")
        self.sent.append(data)

    async def receive_text(self) -> str:
        return "ping"

    async def close(self):
        self.closed = True


# ════════════════════════════════════════════════════
# Case 1: 单客户端 connect + broadcast
# ════════════════════════════════════════════════════

async def test_single_client():
    mgr = WebSocketManager()
    ws = MockWebSocket()

    await mgr.connect("battle-001", ws)
    event = BattleEvent.create(
        BattleEventType.CARD_SUBMITTED, "battle-001",
        {"side": "a", "player_name": "Alice", "card_id": "C01"},
    )
    await mgr.broadcast("battle-001", event)

    assert len(ws.sent) == 1
    msg = json.loads(ws.sent[0])
    assert msg["type"] == "card_submitted"
    assert msg["battle_id"] == "battle-001"
    assert msg["data"]["side"] == "a"

    print("  PASS: single client connect + broadcast")


# ════════════════════════════════════════════════════
# Case 2: 两个客户端同时接收
# ════════════════════════════════════════════════════

async def test_two_clients():
    mgr = WebSocketManager()
    ws1 = MockWebSocket()
    ws2 = MockWebSocket()

    await mgr.connect("battle-002", ws1)
    await mgr.connect("battle-002", ws2)

    event = BattleEvent.create(
        BattleEventType.ROUND_RESOLVED, "battle-002",
        {"round_number": 1, "damage_to_a": 2, "damage_to_b": 0},
    )
    await mgr.broadcast("battle-002", event)

    assert len(ws1.sent) == 1
    assert len(ws2.sent) == 1
    # 两个客户端收到相同的消息
    m1 = json.loads(ws1.sent[0])
    m2 = json.loads(ws2.sent[0])
    assert m1["type"] == m2["type"] == "round_resolved"

    print("  PASS: two clients both receive")


# ════════════════════════════════════════════════════
# Case 3: 断连不影响其他客户端
# ════════════════════════════════════════════════════

async def test_disconnect_isolation():
    mgr = WebSocketManager()
    ws_good = MockWebSocket()
    ws_bad = MockWebSocket(fail_on_send=True)

    await mgr.connect("battle-003", ws_good)
    await mgr.connect("battle-003", ws_bad)

    event = BattleEvent.create(BattleEventType.CARD_SUBMITTED, "battle-003",
                                {"side": "a"})
    await mgr.broadcast("battle-003", event)

    # 正常的客户端收到消息
    assert len(ws_good.sent) == 1
    # 失败的客户端被移除
    assert "battle-003" in mgr._connections
    assert ws_bad not in mgr._connections["battle-003"]
    # 正常客户端仍在连接中
    assert ws_good in mgr._connections["battle-003"]

    print("  PASS: disconnect isolation")


# ════════════════════════════════════════════════════
# Case 4: WebSocket 失败不影响 PersistenceWorker
# ════════════════════════════════════════════════════

def test_ws_failure_doesnt_block_persistence():
    """验证 EventBus 中 WS 推送失败不阻塞 handler"""
    bus = AsyncEventBus(queue_size=32)

    # 创建一个总是失败的 WebSocketManager
    class FailingWSManager:
        async def broadcast(self, battle_id, event):
            raise RuntimeError("WS broadcast simulated failure")

    bus._ws_manager = FailingWSManager()

    handler_called = []

    async def test_handler(event):
        handler_called.append(True)

    bus.subscribe(BattleEventType.CARD_SUBMITTED, test_handler)

    async def run():
        await bus.start()
        event = BattleEvent.create(BattleEventType.CARD_SUBMITTED, "battle-fail",
                                    {"side": "a"})
        bus.emit(event)
        await asyncio.sleep(0.3)
        await bus.stop()

    asyncio.run(run())

    # handler 仍然被调用
    assert len(handler_called) >= 1
    print("  PASS: WS failure doesn't block persistence handler")


# ════════════════════════════════════════════════════
# Case 5: EventBus emit → WebSocket broadcast 集成
# ════════════════════════════════════════════════════

def test_eventbus_ws_integration():
    """验证 EventBus._dispatch_event 中 broadcast 被调用"""
    bus = AsyncEventBus(queue_size=32)

    broadcast_calls = []

    class RecordingWSManager:
        async def broadcast(self, battle_id, event):
            broadcast_calls.append({
                "battle_id": battle_id,
                "type": event.type.value,
            })

    bus._ws_manager = RecordingWSManager()

    handled = []

    async def handler(event):
        handled.append(event.type.value)

    bus.subscribe(BattleEventType.ROUND_RESOLVED, handler)

    async def run():
        await bus.start()
        event = BattleEvent.create(
            BattleEventType.ROUND_RESOLVED, "battle-integ-ws",
            {"round_number": 1},
        )
        bus.emit(event)
        await asyncio.sleep(0.3)
        await bus.stop()

    asyncio.run(run())

    # broadcast 被调用
    assert len(broadcast_calls) >= 1
    assert broadcast_calls[0]["type"] == "round_resolved"
    assert broadcast_calls[0]["battle_id"] == "battle-integ-ws"
    # handler 也被调用
    assert len(handled) >= 1

    print("  PASS: EventBus WS integration")


# ════════════════════════════════════════════════════
# Case 6: 消息格式验证
# ════════════════════════════════════════════════════

async def test_message_format():
    mgr = WebSocketManager()
    ws = MockWebSocket()
    await mgr.connect("battle-fmt", ws)

    # 验证各种事件类型的消息格式
    events = [
        (BattleEventType.BATTLE_CREATED, {"player_a_name": "A", "player_b_name": "B"}),
        (BattleEventType.DECK_CONFIRMED, {"player_a_deck": ["C01"], "player_b_deck": ["C02"]}),
        (BattleEventType.CARD_SUBMITTED, {"side": "a", "card_id": "C01"}),
        (BattleEventType.ROUND_RESOLVED, {"round_number": 5, "hp_a_after": 15}),
        (BattleEventType.BATTLE_FINISHED, {"winner": "Alice", "end_reason": "HP=0"}),
    ]

    for event_type, data in events:
        ws.sent.clear()
        event = BattleEvent.create(event_type, "battle-fmt", data)
        await mgr.broadcast("battle-fmt", event)

        assert len(ws.sent) == 1
        msg = json.loads(ws.sent[0])
        assert "type" in msg
        assert "battle_id" in msg
        assert "timestamp" in msg
        assert "data" in msg
        assert msg["type"] == event_type.value
        assert msg["data"] == data

    print("  PASS: message format correct for all event types")


# ════════════════════════════════════════════════════
# Case 7: 未知 battle_id 的 broadcast 不报错
# ════════════════════════════════════════════════════

async def test_broadcast_no_connections():
    mgr = WebSocketManager()
    event = BattleEvent.create(BattleEventType.CARD_SUBMITTED, "no-connections",
                                {"side": "a"})
    # 不应抛出异常
    await mgr.broadcast("no-connections", event)
    print("  PASS: broadcast with no connections is safe")


# ════════════════════════════════════════════════════
# Case 8: disconnect 清理空 battle
# ════════════════════════════════════════════════════

async def test_disconnect_cleanup():
    mgr = WebSocketManager()
    ws = MockWebSocket()
    await mgr.connect("battle-clean", ws)
    assert "battle-clean" in mgr._connections
    await mgr.disconnect("battle-clean", ws)
    # 连接数为 0 时 battle 应从字典中移除
    assert "battle-clean" not in mgr._connections
    print("  PASS: disconnect cleans up empty battle")


# ════════════════════════════════════════════════════
# Case 9: 现有测试仍然通过
# ════════════════════════════════════════════════════

def test_existing_tests_pass():
    import subprocess
    result = subprocess.run(
        ["python", "tests/test_battle_scenarios.py"],
        capture_output=True,
        cwd="D:/vibecoding/onling-battle-royale/src/judge",
    )
    output = result.stdout.decode("utf-8", errors="replace")
    assert "Results: 8 passed, 0 failed" in output
    print("  PASS: existing 8 tests still pass")


# ════════════════════════════════════════════════════
# 运行
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("WebSocket Tests")
    print("=" * 60)

    asyncio.run(test_single_client())
    asyncio.run(test_two_clients())
    asyncio.run(test_disconnect_isolation())
    test_ws_failure_doesnt_block_persistence()
    test_eventbus_ws_integration()
    asyncio.run(test_message_format())
    asyncio.run(test_broadcast_no_connections())
    asyncio.run(test_disconnect_cleanup())
    test_existing_tests_pass()

    print()
    print("Results: 9 passed, 0 failed, 9 total")
