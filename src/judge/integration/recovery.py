"""
RecoveryManager — 崩溃恢复。

启动时从 Snapshot + EventLog 重建 BattleSession。
恢复过程不调用 BattleManager 方法，不触发 emit，不写 EventLog。

恢复策略:
  1. 加载 snapshot → 创建基础 BattleSession
  2. 读取 snapshot.last_event_id 之后的增量事件
  3. 对每个增量事件调用 _apply_event(session, event)
  4. 将恢复的 session 注入 battle_manager._battles
"""

import logging
from typing import Dict, List, Optional, Any

from engine.battle_manager import BattleSession, BattleManager
from engine.resource_engine import BattleState
from engine.rps_resolver import RPSResolver, RoundResult
from engine.card_library import CARDS_BY_ID
from engine.deck_validator import calculate_available
from engine.events import BattleEvent, BattleEventType
from integration.event_log import EventLog
from integration.snapshot_store import SnapshotStore

logger = logging.getLogger(__name__)


class RecoveryManager:
    """
    崩溃恢复管理器。

    不调用 BattleManager 的状态变更方法（init_battle / confirm_deck / submit_card），
    而是通过 _apply_event 直接修改 BattleSession 内部状态。
    恢复过程不触发 emit，不写 EventLog。
    """

    def __init__(
        self,
        battle_manager: BattleManager,
        snapshot_store: SnapshotStore,
        event_log: EventLog,
    ):
        self._bm = battle_manager
        self._snapshots = snapshot_store
        self._event_log = event_log

    # ════════════════════════════════════════════════════
    # 公共接口
    # ════════════════════════════════════════════════════

    def recover_all_sessions(self) -> int:
        """
        启动时恢复所有未结束对战。

        返回恢复的 session 数量。

        流程:
          1. 列出所有 active snapshots（battle_state != "finished"）
          2. 对每个 snapshot:
             a. 加载 snapshot → 创建基础 BattleSession
             b. 读取 event log → 找到 snapshot 之后的事件
             c. _apply_event 逐个应用增量事件
             d. 注入 battle_manager._battles
        """
        active_ids = self._snapshots.list_active_snapshots()
        if not active_ids:
            logger.info("No active snapshots to recover")
            return 0

        logger.info(f"Starting recovery: {len(active_ids)} active snapshots found")
        recovered = 0

        for battle_id in active_ids:
            try:
                if self._recover_single(battle_id):
                    recovered += 1
            except Exception:
                logger.exception(f"Recovery failed for {battle_id}")

        logger.info(f"Recovery complete: {recovered}/{len(active_ids)} sessions restored")
        return recovered

    # ════════════════════════════════════════════════════
    # 单个 battle 恢复
    # ════════════════════════════════════════════════════

    def _recover_single(self, battle_id: str) -> bool:
        """恢复单个对战"""
        # 如果已存在于内存，跳过
        if battle_id in self._bm._battles:
            logger.info(f"Battle {battle_id} already in memory, skip recovery")
            return False

        # 1. 加载 snapshot
        snapshot = self._snapshots.load(battle_id)
        if snapshot is None:
            logger.warning(f"No snapshot found for {battle_id}, skip")
            return False

        # 2. 创建基础 session
        session = self._session_from_snapshot(snapshot)
        self._bm._battles[battle_id] = session

        # 3. 读取增量事件
        all_events = self._event_log.read(battle_id)
        last_id = snapshot.get("last_event_id", "")
        incremental = _events_after(all_events, last_id)

        if not incremental:
            logger.info(
                f"Recovered {battle_id} from snapshot only "
                f"(r={session.current_round}, state={session.state})"
            )
            return True

        # 4. 逐事件应用
        for event in incremental:
            try:
                _apply_event(session, event)
            except Exception:
                logger.exception(
                    f"Failed to apply event {event.event_id} "
                    f"type={event.type.value} during recovery of {battle_id}"
                )
                # 继续处理后续事件（best-effort）

        logger.info(
            f"Recovered {battle_id}: snapshot + {len(incremental)} events "
            f"(r={session.current_round}, state={session.state})"
        )
        return True

    # ════════════════════════════════════════════════════
    # Snapshot → Session
    # ════════════════════════════════════════════════════

    @staticmethod
    def _session_from_snapshot(s: Dict[str, Any]) -> BattleSession:
        """从 snapshot dict 创建 BattleSession"""

        # 重建 BattleState（保留 aspect_levels 用于 merge）
        state_a = RecoveryManager._build_battle_state(
            s.get("state_a"), s.get("player_a_aspects", {})
        )
        state_b = RecoveryManager._build_battle_state(
            s.get("state_b"), s.get("player_b_aspects", {})
        )

        session = BattleSession(
            id=s["battle_id"],
            player_a_name=s.get("player_a_name", ""),
            player_b_name=s.get("player_b_name", ""),
            player_a_base_token=s.get("player_a_base_token", ""),
            player_b_base_token=s.get("player_b_base_token", ""),
            player_a_aspects=s.get("player_a_aspects", {}),
            player_b_aspects=s.get("player_b_aspects", {}),
            player_a_available=s.get("player_a_available", []),
            player_b_available=s.get("player_b_available", []),
            player_a_deck=s.get("player_a_deck", []),
            player_b_deck=s.get("player_b_deck", []),
            state_a=state_a,
            state_b=state_b,
            current_round=s.get("current_round", 0),
            state=s.get("battle_state", "initialized"),
            submission_a=s.get("submission_a"),
            submission_b=s.get("submission_b"),
            winner=s.get("winner"),
            end_reason=s.get("end_reason", ""),
        )

        # 重建 RPSResolver（如果牌库已存在）
        if session.player_a_deck and session.player_b_deck:
            session.resolver = RPSResolver(
                session.player_a_deck, session.player_b_deck
            )

        return session

    @staticmethod
    def _build_battle_state(
        state_dict: Optional[Dict[str, Any]],
        aspects: Dict[str, int],
    ) -> Optional[BattleState]:
        """从 snapshot 的 state dict 重建 BattleState"""
        if state_dict is None:
            return None
        return BattleState(
            hp=state_dict.get("hp", 20),
            max_hp=state_dict.get("max_hp", 20),
            blade_level=aspects.get("刃", state_dict.get("blade_level", 0)),
            moth_level=aspects.get("蛾", state_dict.get("moth_level", 0)),
            forge_level=aspects.get("铸", state_dict.get("forge_level", 0)),
            winter_level=aspects.get("冬", state_dict.get("winter_level", 0)),
            heart_level=aspects.get("心", state_dict.get("heart_level", 0)),
            lantern_level=aspects.get("灯", state_dict.get("lantern_level", 0)),
            edge=state_dict.get("edge", 0),
            phantom=state_dict.get("phantom", 0),
            charge=state_dict.get("charge", 0),
            self_chill=state_dict.get("self_chill", 0),
            pulse=state_dict.get("pulse", 0),
            read=state_dict.get("read", 0),
            insight=state_dict.get("insight", 0),
        )


# ═══════════════════════════════════════════════════════
# 事件应用（纯函数，直接修改 session）
# ═══════════════════════════════════════════════════════

def _apply_event(session: BattleSession, event: BattleEvent) -> None:
    """
    将单个事件应用到 BattleSession。

    直接修改 session 内部状态，不调用 BattleManager 方法。
    不 emit 事件，不写 EventLog，不触发 PersistenceWorker。
    """
    event_type = event.type
    d = event.data

    if event_type == BattleEventType.BATTLE_CREATED:
        _apply_battle_created(session, d)

    elif event_type == BattleEventType.DECK_CONFIRMED:
        _apply_deck_confirmed(session, d)

    elif event_type == BattleEventType.CARD_SUBMITTED:
        _apply_card_submitted(session, d)

    elif event_type == BattleEventType.ROUND_RESOLVED:
        _apply_round_resolved(session, d)

    elif event_type == BattleEventType.BATTLE_FINISHED:
        _apply_battle_finished(session, d)

    elif event_type == BattleEventType.BATTLE_RESTORED:
        # 恢复事件本身不改变状态，跳过
        pass

    elif event_type == BattleEventType.BATTLE_ERROR:
        # error 事件不改变状态，跳过
        pass


def _apply_battle_created(session: BattleSession, d: Dict[str, Any]) -> None:
    """BATTLE_CREATED → 设置玩家信息 + 可用牌"""
    # session 已由 _session_from_snapshot 创建，此事件在 snapshot 之后重放
    # 只需确认可用牌已计算
    if not session.player_a_available:
        session.player_a_available = [c.id for c in calculate_available(session.player_a_aspects)]
    if not session.player_b_available:
        session.player_b_available = [c.id for c in calculate_available(session.player_b_aspects)]
    session.state = "deck_selection"


def _apply_deck_confirmed(session: BattleSession, d: Dict[str, Any]) -> None:
    """DECK_CONFIRMED → 锁定牌库 + 初始化战斗状态"""
    session.player_a_deck = d.get("player_a_deck", session.player_a_deck)
    session.player_b_deck = d.get("player_b_deck", session.player_b_deck)

    # 初始化 BattleState（如果未设置）
    if session.state_a is None:
        session.state_a = BattleState(
            hp=20,
            blade_level=session.player_a_aspects.get("刃", 0),
            moth_level=session.player_a_aspects.get("蛾", 0),
            forge_level=session.player_a_aspects.get("铸", 0),
            winter_level=session.player_a_aspects.get("冬", 0),
            heart_level=session.player_a_aspects.get("心", 0),
            lantern_level=session.player_a_aspects.get("灯", 0),
        )
    if session.state_b is None:
        session.state_b = BattleState(
            hp=20,
            blade_level=session.player_b_aspects.get("刃", 0),
            moth_level=session.player_b_aspects.get("蛾", 0),
            forge_level=session.player_b_aspects.get("铸", 0),
            winter_level=session.player_b_aspects.get("冬", 0),
            heart_level=session.player_b_aspects.get("心", 0),
            lantern_level=session.player_b_aspects.get("灯", 0),
        )

    # 创建 RPSResolver
    if session.resolver is None and session.player_a_deck and session.player_b_deck:
        session.resolver = RPSResolver(session.player_a_deck, session.player_b_deck)

    session.state = "in_progress"
    session.current_round = 1


def _apply_card_submitted(session: BattleSession, d: Dict[str, Any]) -> None:
    """CARD_SUBMITTED → 记录提交"""
    side = d.get("side", "")
    card_id = d.get("card_id", "")
    if side == "a":
        session.submission_a = card_id
    elif side == "b":
        session.submission_b = card_id


def _apply_round_resolved(session: BattleSession, d: Dict[str, Any]) -> None:
    """ROUND_RESOLVED → 应用结算结果"""
    # 清除提交
    session.submission_a = None
    session.submission_b = None

    battle_ended = d.get("battle_ended", False)
    round_number = d.get("round_number", 0)

    # 应用状态快照
    _apply_state_snapshot(session.state_a, d.get("state_a_snapshot"))
    _apply_state_snapshot(session.state_b, d.get("state_b_snapshot"))

    # 更新回合/状态
    if battle_ended:
        session.state = "finished"
        session.winner = d.get("winner_side")
        session.end_reason = f"Round {round_number} ended"
    else:
        session.current_round = round_number + 1

    # 构建轻量级回合记录（供 replay 显示）
    session.rounds.append(_make_round_result(d))


def _apply_battle_finished(session: BattleSession, d: Dict[str, Any]) -> None:
    """BATTLE_FINISHED → 标记结束"""
    session.state = "finished"
    if d.get("winner"):
        session.winner = d["winner"]
    if d.get("end_reason"):
        session.end_reason = d["end_reason"]


def _apply_state_snapshot(
    bs: Optional[BattleState],
    snapshot: Optional[Dict[str, Any]],
) -> None:
    """将 state snapshot dict 应用到 BattleState 对象"""
    if bs is None or snapshot is None:
        return
    bs.hp = snapshot.get("hp", bs.hp)
    bs.edge = snapshot.get("edge", 0)
    bs.phantom = snapshot.get("phantom", 0)
    bs.charge = snapshot.get("charge", 0)
    bs.self_chill = snapshot.get("chill", 0)
    bs.pulse = snapshot.get("pulse", 0)
    bs.read = snapshot.get("read", 0)
    bs.insight = snapshot.get("insight", 0)


def _make_round_result(d: Dict[str, Any]) -> RoundResult:
    """从 ROUND_RESOLVED event data 构造 RoundResult"""
    card_a = CARDS_BY_ID.get(d.get("card_a_id", ""))
    card_b = CARDS_BY_ID.get(d.get("card_b_id", ""))
    # 兜底：卡牌不存在时用最小对象（不应发生）
    if card_a is None:
        from engine.card_library import Card as CardClass
        card_a = CardClass(id="?", name="?", category="?", aspect="?", level_requirement=0, base_damage=0, defense_value=0, effect_text="")
    if card_b is None:
        from engine.card_library import Card as CardClass
        card_b = CardClass(id="?", name="?", category="?", aspect="?", level_requirement=0, base_damage=0, defense_value=0, effect_text="")

    return RoundResult(
        round_number=d.get("round_number", 0),
        card_a=card_a,
        card_b=card_b,
        rps_type=d.get("rps_description", ""),   # 用 RPS 描述代替类型名
        rps_description=d.get("rps_description", ""),
        damage_to_a=d.get("damage_to_a", 0),
        damage_to_b=d.get("damage_to_b", 0),
        state_a_after=None,   # 不可靠，不从快照逆推
        state_b_after=None,
        resource_logs_a=[],
        resource_logs_b=[],
        special_events=d.get("special_events", []),
        battle_ended=d.get("battle_ended", False),
        winner=d.get("winner_side"),
    )


def _events_after(
    events: List[BattleEvent],
    last_event_id: str,
) -> List[BattleEvent]:
    """过滤出 last_event_id 之后的事件"""
    if not last_event_id:
        logger.info("No last_event_id in snapshot, replaying all events")
        return events

    found = False
    for i, e in enumerate(events):
        if e.event_id == last_event_id:
            found = True
            return events[i + 1:]

    if not found:
        logger.warning(
            f"last_event_id {last_event_id} not found in event log, "
            f"replaying all {len(events)} events"
        )
        return events

    return []
