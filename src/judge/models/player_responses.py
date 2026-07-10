"""
玩家客户端 — 响应模型
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


class PlayerLookupResponse(BaseModel):
    """玩家查找结果"""
    ok: bool = True
    player_name: str = ""
    aspects: Dict[str, int] = {}
    game_hp: int = 0
    has_battle: bool = False
    battle_id: str = ""
    battle_state: str = ""


class MyResources(BaseModel):
    """我的六性相资源 + 看破"""
    edge: int = 0
    phantom: int = 0
    charge: int = 0
    chill: int = 0
    pulse: int = 0
    insight: int = 0
    read: int = 0


class PlayerBattleResponse(BaseModel):
    """玩家视角的战斗状态"""
    ok: bool = True
    battle_id: str = ""
    state: str = ""
    current_round: int = 0
    my_side: str = ""
    opponent_name: str = ""
    my_hp: int = 20
    opponent_hp: int = 20
    my_resources: MyResources = Field(default_factory=MyResources)
    my_deck: List[str] = []
    deck_confirmed: bool = False
    deck_locked: bool = False
    my_submitted_this_round: bool = False
    winner: Optional[str] = None


class AvailableCard(BaseModel):
    """可用卡牌摘要"""
    card_id: str = ""
    name: str = ""
    category: str = ""
    aspect: str = ""
    level_requirement: int = 0
    effect_text: str = ""
    selected: bool = False


class AvailableCardsResponse(BaseModel):
    """可用卡牌列表"""
    ok: bool = True
    battle_id: str = ""
    cards: List[AvailableCard] = []
    selected_count: int = 0
    deck_size: int = 8
    deck_locked: bool = False


class SelectDeckResponse(BaseModel):
    """牌库确认结果"""
    ok: bool = True
    status: str = ""
    current_round: int = 0
    message: str = ""


class RoundResultInfo(BaseModel):
    """单回合结算结果（玩家视角）"""
    my_card: str = ""
    opponent_card: str = ""
    rps_description: str = ""
    damage_to_me: int = 0
    damage_to_opponent: int = 0
    my_hp_after: int = 20
    opponent_hp_after: int = 20
    special_events: List[str] = []


class SubmitCardResponse(BaseModel):
    """出牌提交结果"""
    ok: bool = True
    status: str = ""
    round: int = 0
    result: Optional[RoundResultInfo] = None
    message: str = ""


class BattleLogEntry(BaseModel):
    """战斗日志条目（玩家视角）"""
    round: int = 0
    my_card: str = ""
    opponent_card: str = ""
    rps_description: str = ""
    damage_to_me: int = 0
    damage_to_opponent: int = 0
    my_hp_after: int = 20
    opponent_hp_after: int = 20


class BattleLogsResponse(BaseModel):
    """战斗日志"""
    ok: bool = True
    battle_id: str = ""
    logs: List[BattleLogEntry] = []
