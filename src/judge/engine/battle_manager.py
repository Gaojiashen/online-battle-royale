"""
对战生命周期管理 — 创建/状态/结算/记录
"""
import uuid
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from engine.card_library import Card, CARDS_BY_ID, get_available_cards
from engine.deck_validator import validate_deck, DECK_SIZE, calculate_available
from engine.resource_engine import BattleState
from engine.rps_resolver import RPSResolver, RoundResult
from models import (
    BattleInitRequest, BattleInitResponse, CardInfo,
    DeckConfirmRequest, DeckConfirmResponse,
    WebhookResponse, RoundLog,
    BattleStatusResponse, PlayerStateInfo, BattleHistoryResponse,
)
from engine.events import BattleEvent, BattleEventType, EventBus, NullEventBus

logger = logging.getLogger(__name__)

# State name mapping: PG (Chinese) → BattleSession internal (English)
_STATE_MAP = {
    "已初始化": "deck_selection",
    "选牌中": "deck_selection",
    "对战中": "in_progress",
    "已结束": "finished",
}


def _normalize_state(state_str: str) -> str:
    """Normalize PG state name to BattleSession internal state."""
    return _STATE_MAP.get(state_str, "in_progress")


@dataclass
class BattleSession:
    """一场对战的完整状态"""
    id: str
    player_a_name: str
    player_b_name: str
    player_a_base_token: str
    player_b_base_token: str

    # 玩家性相等级
    player_a_aspects: Dict[str, int] = field(default_factory=dict)
    player_b_aspects: Dict[str, int] = field(default_factory=dict)

    # 牌库
    player_a_available: List[str] = field(default_factory=list)
    player_b_available: List[str] = field(default_factory=list)
    player_a_deck: List[str] = field(default_factory=list)
    player_b_deck: List[str] = field(default_factory=list)

    # 战斗状态
    state_a: Optional[BattleState] = None
    state_b: Optional[BattleState] = None

    # 回合
    current_round: int = 0
    state: str = "initialized"  # initialized | deck_selection | in_progress | finished

    # 提交
    submission_a: Optional[str] = None  # 当前回合A提交的卡牌ID
    submission_b: Optional[str] = None

    # 记录
    rounds: List[RoundResult] = field(default_factory=list)
    winner: Optional[str] = None
    end_reason: str = ""

    # 解析器（初始化时设置）
    resolver: Optional[RPSResolver] = None


class BattleManager:
    """对战管理器"""

    def __init__(self, event_bus: EventBus = None):
        self._battles: Dict[str, BattleSession] = {}
        self._events: EventBus = event_bus if event_bus is not None else NullEventBus()

    async def init_battle(self, req: BattleInitRequest) -> BattleInitResponse:
        """初始化对战"""
        battle_id = str(uuid.uuid4())[:8]

        # 计算双方可用卡牌
        a_available = calculate_available(req.player_a_aspects)
        b_available = calculate_available(req.player_b_aspects)

        session = BattleSession(
            id=battle_id,
            player_a_name=req.player_a_name,
            player_b_name=req.player_b_name,
            player_a_base_token=req.player_a_base_token,
            player_b_base_token=req.player_b_base_token,
            player_a_aspects=req.player_a_aspects,
            player_b_aspects=req.player_b_aspects,
            player_a_available=[c.id for c in a_available],
            player_b_available=[c.id for c in b_available],
            state="deck_selection",
        )

        self._battles[battle_id] = session

        # 发射事件 — 不等待任何副作用
        self._events.emit(BattleEvent.create(
            BattleEventType.BATTLE_CREATED,
            battle_id=battle_id,
            data={
                "player_a_name": req.player_a_name,
                "player_b_name": req.player_b_name,
                "player_a_aspects": req.player_a_aspects,
                "player_b_aspects": req.player_b_aspects,
                "player_a_available": [c.id for c in a_available],
                "player_b_available": [c.id for c in b_available],
            },
        ))

        # Base同步由调用方（init-from-base）处理
        return BattleInitResponse(
            battle_id=battle_id,
            player_a_available=[_card_to_info(c) for c in a_available],
            player_b_available=[_card_to_info(c) for c in b_available],
            message=f"对战创建成功。A可用{len(a_available)}张, B可用{len(b_available)}张。请双方从可用牌中各选{DECK_SIZE}张。",
        )

    def restore_session(self, battle_id: str, player_a_name: str,
                        player_b_name: str, player_a_aspects: Dict[str, int],
                        player_b_aspects: Dict[str, int]):
        """从 Base 数据重建对战会话（服务重启后恢复）"""
        if battle_id in self._battles:
            return  # 已存在，无需重建

        a_available = calculate_available(player_a_aspects)
        b_available = calculate_available(player_b_aspects)

        session = BattleSession(
            id=battle_id,
            player_a_name=player_a_name,
            player_b_name=player_b_name,
            player_a_base_token="",
            player_b_base_token="",
            player_a_aspects=player_a_aspects,
            player_b_aspects=player_b_aspects,
            player_a_available=[c.id for c in a_available],
            player_b_available=[c.id for c in b_available],
            state="deck_selection",
        )
        self._battles[battle_id] = session
        self._events.emit(BattleEvent.create(
            BattleEventType.BATTLE_RESTORED,
            battle_id=battle_id,
            data={
                "player_a_name": player_a_name,
                "player_b_name": player_b_name,
                "player_a_aspects": player_a_aspects,
                "player_b_aspects": player_b_aspects,
                "restore_type": "light",
                "current_round": 0,
                "state": "deck_selection",
            },
        ))
        logger.info(f"Session 从Base恢复: {battle_id} ({player_a_name} vs {player_b_name})")

    def restore_full_session(
        self,
        battle_id: str,
        battle_record: dict,
        state_a_record: dict,
        state_b_record: dict,
        submission_a_card: Optional[str] = None,
        submission_b_card: Optional[str] = None,
    ):
        """从 Base 数据完整恢复运行中的 BattleSession（服务重启后）"""
        if battle_id in self._battles:
            return  # 已存在

        bf = battle_record.get("fields", {})
        player_a_name = bf.get("玩家A名称", "")
        player_b_name = bf.get("玩家B名称", "")
        current_round = int(bf.get("当前回合", 0) or 0)
        state_str = bf.get("状态", "")

        # 解析性相等级 JSON
        import json
        def _parse_aspects(raw):
            if isinstance(raw, str):
                try:
                    return {k: int(v) for k, v in json.loads(raw).items()}
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass
            return {}

        player_a_aspects = _parse_aspects(bf.get("玩家A性相等级", "{}"))
        player_b_aspects = _parse_aspects(bf.get("玩家B性相等级", "{}"))

        # 从 TABLE_PLAYER_STATE 读牌库 (牌位1-8)
        def _read_deck(state_record):
            if not state_record:
                return []
            f = state_record.get("fields", {})
            return [f.get(f"牌位{i}", "") for i in range(1, 9) if f.get(f"牌位{i}")]

        player_a_deck = _read_deck(state_a_record)
        player_b_deck = _read_deck(state_b_record)

        # 从 TABLE_PLAYER_STATE 读 HP 和资源
        def _build_state(state_record, aspects):
            if not state_record:
                return BattleState(hp=20)
            f = state_record.get("fields", {})
            return BattleState(
                hp=int(f.get("战HP", 20) or 20),
                blade_level=aspects.get("刃", 0),
                moth_level=aspects.get("蛾", 0),
                forge_level=aspects.get("铸", 0),
                winter_level=aspects.get("冬", 0),
                heart_level=aspects.get("心", 0),
                lantern_level=aspects.get("灯", 0),
                edge=int(f.get("锋芒", 0) or 0),
                phantom=int(f.get("幻影", 0) or 0),
                charge=int(f.get("蓄力", 0) or 0),
                self_chill=int(f.get("寒意", 0) or 0),
                pulse=int(f.get("脉动", 0) or 0),
                read=int(f.get("洞悉", 0) or 0),
                insight=int(f.get("看破", 0) or 0),
            )

        state_a = _build_state(state_a_record, player_a_aspects)
        state_b = _build_state(state_b_record, player_b_aspects)

        # 恢复提交状态
        def _get_submitted(state_record):
            if not state_record:
                return False
            return state_record.get("fields", {}).get("已提交", False) or False

        submission_a = submission_a_card if _get_submitted(state_a_record) else None
        submission_b = submission_b_card if _get_submitted(state_b_record) else None

        # 重建 session
        a_available = calculate_available(player_a_aspects)
        b_available = calculate_available(player_b_aspects)

        session = BattleSession(
            id=battle_id,
            player_a_name=player_a_name,
            player_b_name=player_b_name,
            player_a_base_token="",
            player_b_base_token="",
            player_a_aspects=player_a_aspects,
            player_b_aspects=player_b_aspects,
            player_a_available=[c.id for c in a_available],
            player_b_available=[c.id for c in b_available],
            player_a_deck=player_a_deck,
            player_b_deck=player_b_deck,
            state_a=state_a,
            state_b=state_b,
            current_round=current_round,
            state=(_normalize_state(state_str) if state_str else "in_progress"),
            submission_a=submission_a,
            submission_b=submission_b,
            winner=bf.get("胜者", "") or None,
        )

        if player_a_deck and player_b_deck:
            session.resolver = RPSResolver(player_a_deck, player_b_deck)

        self._battles[battle_id] = session
        self._events.emit(BattleEvent.create(
            BattleEventType.BATTLE_RESTORED,
            battle_id=battle_id,
            data={
                "player_a_name": player_a_name,
                "player_b_name": player_b_name,
                "player_a_aspects": player_a_aspects,
                "player_b_aspects": player_b_aspects,
                "restore_type": "full",
                "current_round": current_round,
                "state": state_str,
            },
        ))
        logger.info(f"Session 完整恢复: {battle_id} r={current_round} {player_a_name}(HP={state_a.hp}) vs {player_b_name}(HP={state_b.hp}) sub_a={submission_a} sub_b={submission_b}")

    async def confirm_deck(self, req: DeckConfirmRequest) -> DeckConfirmResponse:
        """确认牌库，开始对战"""
        session = self._battles.get(req.battle_id)
        if not session:
            raise ValueError(f"对战不存在: {req.battle_id}（服务可能已重启，请重新发起对战）")

        # 校验牌库
        result_a = validate_deck(req.player_a_deck, session.player_a_aspects)
        result_b = validate_deck(req.player_b_deck, session.player_b_aspects)

        errors = []
        if not result_a.is_valid:
            errors.extend([f"A: {e}" for e in result_a.errors])
        if not result_b.is_valid:
            errors.extend([f"B: {e}" for e in result_b.errors])

        if errors:
            raise ValueError("牌库校验失败:\n" + "\n".join(errors))

        session.player_a_deck = req.player_a_deck
        session.player_b_deck = req.player_b_deck

        # 初始化战斗状态
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

        session.resolver = RPSResolver(req.player_a_deck, req.player_b_deck)
        session.current_round = 1
        session.state = "in_progress"

        self._events.emit(BattleEvent.create(
            BattleEventType.DECK_CONFIRMED,
            battle_id=req.battle_id,
            data={
                "player_a_deck": req.player_a_deck,
                "player_b_deck": req.player_b_deck,
                "current_round": 1,
            },
        ))

        return DeckConfirmResponse(
            battle_id=req.battle_id,
            state="in_progress",
            current_round=1,
            message=f"牌库已锁定。第1回合开始！",
        )

    def submit_card(self, battle_id: str, side: str, card_id: str):
        """玩家提交卡牌 → 返回 WebhookResponse"""
        session = self._battles.get(battle_id)
        if not session:
            return WebhookResponse(status="error",
                                   message=f"对战 {battle_id} 状态丢失（服务可能已重启），请重新发起对战")

        if session.state != "in_progress":
            return WebhookResponse(battle_id=battle_id, status="error",
                                   message=f"对战不在进行中: {session.state}")

        # 校验卡牌在牌库中
        deck = session.player_a_deck if side == "a" else session.player_b_deck
        if card_id not in deck:
            return WebhookResponse(battle_id=battle_id, status="error",
                                   message=f"卡牌 {card_id} 不在本场牌库中")

        # 存储提交
        player_name = session.player_a_name if side == "a" else session.player_b_name
        if side == "a":
            session.submission_a = card_id
        else:
            session.submission_b = card_id

        # 发射事件 — 不等待持久化
        self._events.emit(BattleEvent.create(
            BattleEventType.CARD_SUBMITTED,
            battle_id=battle_id,
            data={
                "side": side,
                "player_name": player_name,
                "card_id": card_id,
                "current_round": session.current_round,
            },
        ))

        # 检查双方是否都提交了
        if session.submission_a and session.submission_b:
            return self._resolve_round(session)

        other_side = "b" if side == "a" else "a"
        return WebhookResponse(
            battle_id=battle_id,
            round=session.current_round,
            status="waiting_for_opponent",
            message=f"等待对手({other_side})提交",
        )

    def _resolve_round(self, session: BattleSession):
        """结算当前回合 → 返回 WebhookResponse"""
        resolver = session.resolver
        state_a = session.state_a
        state_b = session.state_b

        try:
            result = resolver.resolve_round(
                session.current_round,
                session.submission_a,
                session.submission_b,
                state_a, state_b,
            )

            session.rounds.append(result)

            # 清除提交
            session.submission_a = None
            session.submission_b = None

            battle_ended = result.battle_ended
            if battle_ended:
                session.state = "finished"
                session.winner = result.winner
                session.end_reason = result.end_reason
            else:
                session.current_round += 1

            # 构建状态快照（供持久化使用）
            state_a_snapshot = {
                "hp": state_a.hp, "edge": state_a.edge,
                "phantom": state_a.phantom, "charge": state_a.charge,
                "chill": state_a.self_chill, "pulse": state_a.pulse,
                "read": state_a.read, "insight": state_a.insight,
            } if state_a else None
            state_b_snapshot = {
                "hp": state_b.hp, "edge": state_b.edge,
                "phantom": state_b.phantom, "charge": state_b.charge,
                "chill": state_b.self_chill, "pulse": state_b.pulse,
                "read": state_b.read, "insight": state_b.insight,
            } if state_b else None

            # 发射 ROUND_RESOLVED 事件（PersistenceWorker 后台消费）
            self._events.emit(BattleEvent.create(
                BattleEventType.ROUND_RESOLVED,
                battle_id=session.id,
                data={
                    "round_number": result.round_number,
                    "card_a_id": result.card_a.id,
                    "card_a_name": result.card_a.name,
                    "card_b_id": result.card_b.id,
                    "card_b_name": result.card_b.name,
                    "rps_description": result.rps_description,
                    "damage_to_a": result.damage_to_a,
                    "damage_to_b": result.damage_to_b,
                    "hp_a_after": state_a.hp if state_a else 0,
                    "hp_b_after": state_b.hp if state_b else 0,
                    "special_events": list(result.special_events),
                    "battle_ended": battle_ended,
                    "winner_side": result.winner,
                    "state_a_snapshot": state_a_snapshot,
                    "state_b_snapshot": state_b_snapshot,
                },
            ))

            # 对战结束 → 额外触发 BATTLE_FINISHED
            if battle_ended:
                self._events.emit(BattleEvent.create(
                    BattleEventType.BATTLE_FINISHED,
                    battle_id=session.id,
                    data={
                        "winner": result.winner,
                        "end_reason": result.end_reason,
                        "final_round": result.round_number,
                    },
                ))

            return WebhookResponse(
                battle_id=session.id,
                round=result.round_number,
                status="resolved",
                result=_round_to_log(result),
                message="结算完成" if not battle_ended else f"战斗结束！胜者: {result.winner}",
            )

        except Exception as e:
            # 清除失败的提交
            session.submission_a = None
            session.submission_b = None

            self._events.emit(BattleEvent.create(
                BattleEventType.BATTLE_ERROR,
                battle_id=session.id,
                data={"context": "_resolve_round", "error": str(e)},
            ))

            return WebhookResponse(
                battle_id=session.id,
                round=session.current_round,
                status="error",
                message=str(e),
            )

    def get_status(self, battle_id: str) -> Optional[BattleStatusResponse]:
        """查询对战状态"""
        session = self._battles.get(battle_id)
        if not session:
            return None

        a_info = None
        b_info = None
        if session.state_a:
            a_info = PlayerStateInfo(
                name=session.player_a_name,
                hp=session.state_a.hp,
                edge=session.state_a.edge,
                phantom=session.state_a.phantom,
                charge=session.state_a.charge,
                self_chill=session.state_a.self_chill,
                pulse=session.state_a.pulse,
                read=session.state_a.read,
                insight=session.state_a.insight,
                submitted=session.submission_a is not None,
            )
        if session.state_b:
            b_info = PlayerStateInfo(
                name=session.player_b_name,
                hp=session.state_b.hp,
                edge=session.state_b.edge,
                phantom=session.state_b.phantom,
                charge=session.state_b.charge,
                self_chill=session.state_b.self_chill,
                pulse=session.state_b.pulse,
                read=session.state_b.read,
                insight=session.state_b.insight,
                submitted=session.submission_b is not None,
            )

        return BattleStatusResponse(
            battle_id=battle_id,
            state=session.state,
            current_round=session.current_round,
            player_a=a_info,
            player_b=b_info,
            winner=session.winner,
        )

    def get_history(self, battle_id: str) -> Optional[BattleHistoryResponse]:
        """获取完整战斗记录"""
        session = self._battles.get(battle_id)
        if not session:
            return None

        return BattleHistoryResponse(
            battle_id=battle_id,
            state=session.state,
            rounds=[_round_to_log(r) for r in session.rounds],
            winner=session.winner,
            end_reason=session.end_reason,
        )


# ════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════

def _card_to_info(card: Card) -> CardInfo:
    return CardInfo(
        id=card.id,
        name=card.name,
        category=card.category,
        aspect=card.aspect,
        level_requirement=card.level_requirement,
        effect_text=card.effect_text,
    )


def _round_to_log(r: RoundResult) -> RoundLog:
    return RoundLog(
        round_number=r.round_number,
        card_a_name=f"{r.card_a.id} {r.card_a.name}",
        card_b_name=f"{r.card_b.id} {r.card_b.name}",
        rps_description=r.rps_description,
        damage_to_a=r.damage_to_a,
        damage_to_b=r.damage_to_b,
        hp_a_after=r.state_a_after.hp if r.state_a_after else 0,
        hp_b_after=r.state_b_after.hp if r.state_b_after else 0,
        resource_logs_a=r.resource_logs_a,
        resource_logs_b=r.resource_logs_b,
        special_events=r.special_events,
        battle_ended=r.battle_ended,
        winner=r.winner,
    )
