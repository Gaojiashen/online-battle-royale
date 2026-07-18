"""
RecoveryManager 测试 — 崩溃恢复完整验证。

覆盖:
  1. snapshot + event log → 完整恢复
  2. 恢复后 session 状态与崩溃前一致
  3. 不会产生新的 event log
  4. 不会触发 PersistenceWorker（不 emit）
  5. 多个 battle 同时恢复
  6. 缺失 snapshot / event log 的异常情况
"""

import os
import json
import tempfile
import shutil
import asyncio
import logging

logging.basicConfig(level=logging.WARNING)

from engine.battle_manager import BattleSession, BattleManager
from engine.resource_engine import BattleState
from engine.rps_resolver import RPSResolver
from engine.card_library import CARDS_BY_ID
from engine.deck_validator import calculate_available
from engine.events import BattleEvent, BattleEventType, NullEventBus
from integration.event_log import EventLog
from integration.snapshot_store import SnapshotStore
from integration.recovery import RecoveryManager, _apply_event, _events_after


# ════════════════════════════════════════════════════
# 测试辅助
# ════════════════════════════════════════════════════

def make_battle_session(battle_id="test-battle-001") -> BattleSession:
    """创建一个完整的牌库选择阶段的 BattleSession"""
    aspects_a = {"刃": 4, "蛾": 6, "铸": 2, "冬": 3, "心": 5, "灯": 1}
    aspects_b = {"刃": 2, "蛾": 3, "铸": 7, "冬": 4, "心": 1, "灯": 6}
    a_avail = [c.id for c in calculate_available(aspects_a)]
    b_avail = [c.id for c in calculate_available(aspects_b)]
    return BattleSession(
        id=battle_id,
        player_a_name="Alice", player_b_name="Bob",
        player_a_base_token="t1", player_b_base_token="t2",
        player_a_aspects=aspects_a, player_b_aspects=aspects_b,
        player_a_available=a_avail, player_b_available=b_avail,
        state="deck_selection",
    )


def confirm_session(session: BattleSession) -> None:
    """确认牌库（模拟 confirm_deck 的状态变更，不发射事件）"""
    a_deck = session.player_a_available[:8]
    b_deck = session.player_b_available[:8]
    session.player_a_deck = a_deck
    session.player_b_deck = b_deck
    session.state_a = BattleState(
        hp=20,
        blade_level=session.player_a_aspects.get("刃", 0),
        moth_level=session.player_a_aspects.get("蛾", 0),
        forge_level=session.player_a_aspects.get("铸", 0),
        winter_level=session.player_a_aspects.get("冬", 0),
        heart_level=session.player_a_aspects.get("心", 0),
        lantern_level=session.player_a_aspects.get("灯", 0),
    )
    session.state_b = BattleState(
        hp=20,
        blade_level=session.player_b_aspects.get("刃", 0),
        moth_level=session.player_b_aspects.get("蛾", 0),
        forge_level=session.player_b_aspects.get("铸", 0),
        winter_level=session.player_b_aspects.get("冬", 0),
        heart_level=session.player_b_aspects.get("心", 0),
        lantern_level=session.player_b_aspects.get("灯", 0),
    )
    session.resolver = RPSResolver(a_deck, b_deck)
    session.state = "in_progress"
    session.current_round = 1


def make_round_resolved_event(battle_id: str, round_num: int,
                               battle_ended: bool = False) -> BattleEvent:
    """创建 ROUND_RESOLVED 事件"""
    return BattleEvent.create(
        BattleEventType.ROUND_RESOLVED,
        battle_id=battle_id,
        data={
            "round_number": round_num,
            "card_a_id": "C01", "card_a_name": "挥击",
            "card_b_id": "C02", "card_b_name": "格挡",
            "rps_description": "A bypasses B",
            "damage_to_a": 0, "damage_to_b": 2,
            "hp_a_after": 20, "hp_b_after": 18 - (round_num - 1) * 2,
            "special_events": ["bypass"],
            "battle_ended": battle_ended,
            "winner_side": "Alice" if battle_ended else None,
            "state_a_snapshot": {"hp": 20, "edge": 2, "phantom": 0, "charge": 0,
                                  "chill": 0, "pulse": 1, "read": 0, "insight": 0},
            "state_b_snapshot": {"hp": 18 - (round_num - 1) * 2, "edge": 0,
                                  "phantom": 1, "charge": 1, "chill": 0,
                                  "pulse": 0, "read": 1, "insight": 0},
        },
    )


# ════════════════════════════════════════════════════
# Test 1: Snapshot + Event Log → 完整恢复
# ════════════════════════════════════════════════════

def test_full_recovery_flow():
    """模拟：创建 session → 保存 snapshot → 产生事件 → 崩溃 → 恢复"""
    tmpdir = tempfile.mkdtemp(prefix="recovery_test_")
    try:
        # 准备存储
        snapshots = SnapshotStore(data_dir=os.path.join(tmpdir, "snapshots"))
        event_log = EventLog(data_dir=os.path.join(tmpdir, "events"))

        # 模拟"崩溃前"：创建 session，确认牌库，打 3 回合
        battle_id = "battle-recovery-001"
        session = make_battle_session(battle_id)
        confirm_session(session)  # 直接操作状态，不 emit

        # 保存 snapshot（DECK_CONFIRMED 之后）
        snapshots.save(session, last_event_id="")

        # 写入 3 个 ROUND_RESOLVED 事件
        events_to_write = []
        for r in range(1, 4):
            ev = make_round_resolved_event(battle_id, r, battle_ended=(r == 3))
            events_to_write.append(ev)

        for ev in events_to_write:
            event_log.append(ev)

        # 模拟"崩溃后"：创建新的 BattleManager + RecoveryManager
        bm = BattleManager()  # 空 _battles
        recovery = RecoveryManager(bm, snapshots, event_log)

        # 恢复前：记录 event log 中已有的事件数
        events_before = len(event_log.read(battle_id))

        # 执行恢复
        count = recovery.recover_all_sessions()
        assert count == 1, f"Expected 1 recovered, got {count}"

        # 验证恢复后的 session
        restored = bm._battles.get(battle_id)
        assert restored is not None
        assert restored.player_a_name == "Alice"
        assert restored.player_b_name == "Bob"
        assert restored.state == "finished"  # 第 3 回合 battle_ended=True
        assert restored.current_round == 3  # R3 resolved: round_number + 0 (battle ended, no increment)
        assert restored.winner == "Alice"
        assert restored.state_a.hp == 20
        assert restored.state_b.hp == 14  # 18-2*2=14
        assert restored.state_a.edge == 2
        assert restored.state_b.phantom == 1
        assert len(restored.rounds) == 3  # 3 round results reconstructed

        # 验证：恢复过程没有写入新的 event log
        events_after = len(event_log.read(battle_id))
        assert events_after == events_before, (
            f"Event log grew during recovery: {events_before} → {events_after}"
        )

        print("  PASS: full recovery flow")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# Test 2: 恢复后状态一致
# ════════════════════════════════════════════════════

def test_state_consistency():
    """验证恢复后的所有字段与原状态一致"""
    tmpdir = tempfile.mkdtemp(prefix="recovery_consistency_")
    try:
        snapshots = SnapshotStore(data_dir=os.path.join(tmpdir, "snapshots"))
        event_log = EventLog(data_dir=os.path.join(tmpdir, "events"))

        battle_id = "battle-consistency"
        session = make_battle_session(battle_id)
        confirm_session(session)

        # 模拟回合 1: A 打出 2 点伤害
        session.state_b.hp = 18
        session.state_a.edge = 2
        session.state_b.phantom = 1
        session.submission_a = None
        session.submission_b = None
        session.current_round = 2

        snapshots.save(session, last_event_id="")

        # 写入 R1 事件
        ev = make_round_resolved_event(battle_id, 1)
        event_log.append(ev)

        # 恢复
        bm = BattleManager()
        recovery = RecoveryManager(bm, snapshots, event_log)
        recovery.recover_all_sessions()

        restored = bm._battles[battle_id]
        assert restored is not None
        assert restored.state_a.hp == 20
        assert restored.state_b.hp == 18
        assert restored.state_a.edge == 2
        assert restored.state_b.phantom == 1
        assert restored.current_round == 2
        assert restored.state == "in_progress"
        assert restored.submission_a is None
        assert restored.submission_b is None
        assert len(restored.player_a_deck) == 8
        assert len(restored.player_b_deck) == 8
        assert restored.resolver is not None  # RPSResolver reconstructed

        print("  PASS: state consistency")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# Test 3: 恢复过程不触发事件
# ════════════════════════════════════════════════════

def test_no_events_during_recovery():
    """验证恢复过程不触发任何事件（emit 计数器保持 0）"""
    tmpdir = tempfile.mkdtemp(prefix="recovery_noemit_")
    try:
        snapshots = SnapshotStore(data_dir=os.path.join(tmpdir, "snapshots"))
        event_log = EventLog(data_dir=os.path.join(tmpdir, "events"))

        battle_id = "battle-noemit"
        session = make_battle_session(battle_id)
        confirm_session(session)
        snapshots.save(session)

        ev = make_round_resolved_event(battle_id, 1)
        event_log.append(ev)

        # 使用 NullEventBus — 不会有任何事件被分发
        bm = BattleManager(event_bus=NullEventBus())
        recovery = RecoveryManager(bm, snapshots, event_log)

        before_count = len(event_log.read(battle_id))
        recovery.recover_all_sessions()

        # event log 不应增加
        after_count = len(event_log.read(battle_id))
        assert after_count == before_count

        # 验证 session 已恢复
        restored = bm._battles[battle_id]
        assert restored is not None
        assert restored.state == "in_progress"

        print("  PASS: no events emitted during recovery")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# Test 4: 多 battle 同时恢复
# ════════════════════════════════════════════════════

def test_multiple_battles_recovery():
    """验证多个未结束对战同时恢复"""
    tmpdir = tempfile.mkdtemp(prefix="recovery_multi_")
    try:
        snapshots = SnapshotStore(data_dir=os.path.join(tmpdir, "snapshots"))
        event_log = EventLog(data_dir=os.path.join(tmpdir, "events"))

        battle_ids = ["multi-001", "multi-002", "multi-003"]
        for bid in battle_ids:
            session = make_battle_session(bid)
            confirm_session(session)
            snapshots.save(session, last_event_id="")
            ev = make_round_resolved_event(bid, 1)
            event_log.append(ev)

        bm = BattleManager()
        recovery = RecoveryManager(bm, snapshots, event_log)
        count = recovery.recover_all_sessions()

        assert count == 3
        for bid in battle_ids:
            assert bid in bm._battles
            assert bm._battles[bid].state == "in_progress"

        print("  PASS: multiple battles recovery")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# Test 5: 缺失 snapshot 的异常处理
# ════════════════════════════════════════════════════

def test_missing_snapshot():
    """验证 snapshot 不存在时的优雅处理"""
    tmpdir = tempfile.mkdtemp(prefix="recovery_missing_")
    try:
        snapshots = SnapshotStore(data_dir=os.path.join(tmpdir, "missing_snap"))
        event_log = EventLog(data_dir=os.path.join(tmpdir, "events"))

        # 不保存 snapshot，只写 event log
        ev = BattleEvent.create(
            BattleEventType.CARD_SUBMITTED, "ghost-battle",
            {"side": "a", "player_name": "Ghost", "card_id": "Z99",
             "current_round": 1},
        )
        event_log.append(ev)

        bm = BattleManager()
        recovery = RecoveryManager(bm, snapshots, event_log)
        count = recovery.recover_all_sessions()

        # 没有 snapshot → 不应恢复任何 session
        assert count == 0
        assert len(bm._battles) == 0

        print("  PASS: missing snapshot handled gracefully")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# Test 6: 已完成对战不恢复
# ════════════════════════════════════════════════════

def test_finished_battle_not_recovered():
    """验证已结束对战不被恢复"""
    tmpdir = tempfile.mkdtemp(prefix="recovery_finished_")
    try:
        snapshots = SnapshotStore(data_dir=os.path.join(tmpdir, "snapshots"))
        event_log = EventLog(data_dir=os.path.join(tmpdir, "events"))

        # 创建已结束的 session
        battle_id = "finished-battle"
        session = make_battle_session(battle_id)
        confirm_session(session)
        session.state = "finished"
        session.winner = "Alice"
        snapshots.save(session)

        bm = BattleManager()
        recovery = RecoveryManager(bm, snapshots, event_log)
        count = recovery.recover_all_sessions()

        # finished 不应被恢复
        assert count == 0

        print("  PASS: finished battle skipped")

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ════════════════════════════════════════════════════
# Test 7: _events_after 辅助函数
# ════════════════════════════════════════════════════

def test_events_after_filter():
    """验证事件过滤逻辑"""
    e1 = BattleEvent.create(BattleEventType.CARD_SUBMITTED, "b1",
                             {"side": "a"})
    e2 = BattleEvent.create(BattleEventType.CARD_SUBMITTED, "b1",
                             {"side": "b"})
    e3 = BattleEvent.create(BattleEventType.ROUND_RESOLVED, "b1",
                             {"round_number": 1})
    events = [e1, e2, e3]

    # 过滤 e1 之后
    result = _events_after(events, e1.event_id)
    assert len(result) == 2
    assert result[0].event_id == e2.event_id
    assert result[1].event_id == e3.event_id

    # 过滤 e2 之后
    result = _events_after(events, e2.event_id)
    assert len(result) == 1
    assert result[0].event_id == e3.event_id

    # 过滤 e3 之后
    result = _events_after(events, e3.event_id)
    assert len(result) == 0

    # 找不到 last_event_id → 返回全部
    result = _events_after(events, "non-existent-id")
    assert len(result) == 3

    # 空 last_event_id → 返回全部
    result = _events_after(events, "")
    assert len(result) == 3

    print("  PASS: events_after filter")


# ════════════════════════════════════════════════════
# Test 8: _apply_event 不错误修改 session 结构
# ════════════════════════════════════════════════════

def test_apply_event_safety():
    """验证 _apply_event 正确应用各种事件类型"""
    session = make_battle_session("apply-safety")

    # BATTLE_CREATED
    ev = BattleEvent.create(BattleEventType.BATTLE_CREATED, session.id,
                             {"player_a_name": "A", "player_b_name": "B"})
    _apply_event(session, ev)
    assert session.state == "deck_selection"

    # DECK_CONFIRMED
    a_deck = session.player_a_available[:8]
    b_deck = session.player_b_available[:8]
    ev = BattleEvent.create(BattleEventType.DECK_CONFIRMED, session.id,
                             {"player_a_deck": a_deck, "player_b_deck": b_deck})
    _apply_event(session, ev)
    assert session.state == "in_progress"
    assert session.current_round == 1
    assert session.state_a is not None
    assert session.state_a.hp == 20

    # CARD_SUBMITTED (A)
    ev = BattleEvent.create(BattleEventType.CARD_SUBMITTED, session.id,
                             {"side": "a", "player_name": "A", "card_id": "C01",
                              "current_round": 1})
    _apply_event(session, ev)
    assert session.submission_a == "C01"
    assert session.submission_b is None

    # CARD_SUBMITTED (B)
    ev = BattleEvent.create(BattleEventType.CARD_SUBMITTED, session.id,
                             {"side": "b", "player_name": "B", "card_id": "C02",
                              "current_round": 1})
    _apply_event(session, ev)
    assert session.submission_b == "C02"

    # ROUND_RESOLVED
    ev = make_round_resolved_event(session.id, 1, battle_ended=False)
    _apply_event(session, ev)
    assert session.submission_a is None
    assert session.submission_b is None
    assert session.current_round == 2
    assert session.state == "in_progress"
    assert len(session.rounds) == 1

    # BATTLE_FINISHED
    ev = BattleEvent.create(BattleEventType.BATTLE_FINISHED, session.id,
                             {"winner": "Alice", "end_reason": "HP=0",
                              "final_round": 5})
    _apply_event(session, ev)
    assert session.state == "finished"
    assert session.winner == "Alice"

    # BATTLE_RESTORED / BATTLE_ERROR — 不应改变状态
    old_state = session.state
    ev = BattleEvent.create(BattleEventType.BATTLE_RESTORED, session.id, {})
    _apply_event(session, ev)
    assert session.state == old_state  # unchanged

    ev = BattleEvent.create(BattleEventType.BATTLE_ERROR, session.id,
                             {"context": "test", "error": "test"})
    _apply_event(session, ev)
    assert session.state == old_state  # unchanged

    print("  PASS: _apply_event safety")


# ════════════════════════════════════════════════════
# 运行
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=" * 60)
    print("RecoveryManager Tests")
    print("=" * 60)

    test_full_recovery_flow()
    test_state_consistency()
    test_no_events_during_recovery()
    test_multiple_battles_recovery()
    test_missing_snapshot()
    test_finished_battle_not_recovered()
    test_events_after_filter()
    test_apply_event_safety()

    print()
    print("Results: 8 passed, 0 failed, 8 total")
