"""
Pydantic 响应模型 — API 响应
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


# ════════════════════════════════════════════════════
# 响应模型
# ════════════════════════════════════════════════════

class CardInfo(BaseModel):
    """卡牌摘要"""
    id: str
    name: str
    category: str
    aspect: str
    level_requirement: int
    effect_text: str


class BattleInitResponse(BaseModel):
    """创建对战响应"""
    ok: bool = True
    battle_id: str
    player_a_available: List[CardInfo] = []
    player_b_available: List[CardInfo] = []
    message: str = ""


class DeckConfirmResponse(BaseModel):
    """确认牌库响应"""
    ok: bool = True
    battle_id: str
    state: str  # "in_progress"
    current_round: int = 1
    message: str = ""


class RoundLog(BaseModel):
    """单回合记录"""
    round_number: int
    card_a_name: str
    card_b_name: str
    rps_description: str
    damage_to_a: int
    damage_to_b: int
    hp_a_after: int
    hp_b_after: int
    resource_logs_a: List[str] = []
    resource_logs_b: List[str] = []
    special_events: List[str] = []
    battle_ended: bool = False
    winner: Optional[str] = None


class WebhookResponse(BaseModel):
    """Webhook响应"""
    ok: bool = True
    battle_id: str = ""
    round: int = 0
    status: str  # "waiting_for_opponent" | "resolved" | "error"
    result: Optional[RoundLog] = None
    message: str = ""


class PlayerStateInfo(BaseModel):
    """玩家状态快照"""
    name: str
    hp: int
    edge: int = 0
    phantom: int = 0
    charge: int = 0
    self_chill: int = 0
    pulse: int = 0
    read: int = 0
    insight: int = 0
    submitted: bool = False


class BattleStatusResponse(BaseModel):
    """对战状态响应"""
    ok: bool = True
    battle_id: str
    state: str  # "initialized" | "deck_selection" | "in_progress" | "finished"
    current_round: int = 0
    player_a: Optional[PlayerStateInfo] = None
    player_b: Optional[PlayerStateInfo] = None
    winner: Optional[str] = None


class BattleHistoryResponse(BaseModel):
    """战斗记录响应"""
    ok: bool = True
    battle_id: str
    state: str
    rounds: List[RoundLog] = []
    winner: Optional[str] = None
    end_reason: str = ""
