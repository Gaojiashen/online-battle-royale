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
from integration.base_sync import base_sync

logger = logging.getLogger(__name__)


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

    def __init__(self):
        self._battles: Dict[str, BattleSession] = {}

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
        logger.info(f"Session 从Base恢复: {battle_id} ({player_a_name} vs {player_b_name})")

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

        # 异步同步到飞书Base
        import asyncio
        asyncio.create_task(base_sync.sync_battle_started(battle_id=req.battle_id))

        return DeckConfirmResponse(
            battle_id=req.battle_id,
            state="in_progress",
            current_round=1,
            message=f"牌库已锁定。第1回合开始！",
        )

    def submit_card(self, battle_id: str, side: str, card_id: str):
        """玩家提交卡牌 → 返回 (WebhookResponse, Optional[Task])"""
        session = self._battles.get(battle_id)
        if not session:
            return WebhookResponse(status="error",
                                   message=f"对战 {battle_id} 状态丢失（服务可能已重启），请重新发起对战"), None

        if session.state != "in_progress":
            return WebhookResponse(battle_id=battle_id, status="error",
                                   message=f"对战不在进行中: {session.state}"), None

        # 校验卡牌在牌库中
        deck = session.player_a_deck if side == "a" else session.player_b_deck
        if card_id not in deck:
            return WebhookResponse(battle_id=battle_id, status="error",
                                   message=f"卡牌 {card_id} 不在本场牌库中"), None

        # 存储提交
        player_name = session.player_a_name if side == "a" else session.player_b_name
        if side == "a":
            session.submission_a = card_id
        else:
            session.submission_b = card_id

        # 异步同步提交到飞书Base
        import asyncio
        asyncio.create_task(base_sync.sync_submission_made(
            battle_id=battle_id, side=side,
            player_name=player_name, card_id=card_id,
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
        ), None

    def _resolve_round(self, session: BattleSession):
        """结算当前回合 → 返回 (WebhookResponse, Optional[Task])"""
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

            if result.battle_ended:
                session.state = "finished"
                session.winner = result.winner
                session.end_reason = result.end_reason
            else:
                session.current_round += 1

            # 同步回合结果到飞书Base
            import asyncio
            state_a_dict = {
                "hp": state_a.hp, "edge": state_a.edge,
                "phantom": state_a.phantom, "charge": state_a.charge,
                "chill": state_a.self_chill, "pulse": state_a.pulse,
                "read": state_a.read, "insight": state_a.insight,
            } if state_a else None
            state_b_dict = {
                "hp": state_b.hp, "edge": state_b.edge,
                "phantom": state_b.phantom, "charge": state_b.charge,
                "chill": state_b.self_chill, "pulse": state_b.pulse,
                "read": state_b.read, "insight": state_b.insight,
            } if state_b else None
            sync_coro = base_sync.sync_round_result(
                battle_id=session.id,
                round_number=result.round_number,
                card_a_name=f"{result.card_a.id} {result.card_a.name}",
                card_b_name=f"{result.card_b.id} {result.card_b.name}",
                rps_description=result.rps_description,
                damage_to_a=result.damage_to_a,
                damage_to_b=result.damage_to_b,
                hp_a_after=state_a.hp if state_a else 0,
                hp_b_after=state_b.hp if state_b else 0,
                special_events=list(result.special_events),
                winner=result.winner,
                battle_ended=result.battle_ended,
                state_a=state_a_dict,
                state_b=state_b_dict,
            )

            response = WebhookResponse(
                battle_id=session.id,
                round=result.round_number,
                status="resolved",
                result=_round_to_log(result),
                message="结算完成" if not result.battle_ended else f"战斗结束！胜者: {result.winner}",
            )

            # 战斗结束时返回 sync task 供调用方 await
            if result.battle_ended:
                return response, asyncio.create_task(sync_coro)
            else:
                asyncio.create_task(sync_coro)
                return response, None

        except Exception as e:
            # 清除失败的提交
            session.submission_a = None
            session.submission_b = None
            return WebhookResponse(
                battle_id=session.id,
                round=session.current_round,
                status="error",
                message=str(e),
            ), None

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
