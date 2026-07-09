"""
Pydantic 数据模型 — API 请求/响应
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any


# ════════════════════════════════════════════════════
# 请求模型
# ════════════════════════════════════════════════════

class BattleInitRequest(BaseModel):
    """创建对战请求"""
    player_a_base_token: str = Field(..., description="玩家A的Base token")
    player_b_base_token: str = Field(..., description="玩家B的Base token")
    player_a_name: str = Field(..., description="玩家A名称")
    player_b_name: str = Field(..., description="玩家B名称")
    player_a_aspects: Dict[str, int] = Field(..., description="玩家A各性相等级 {'灯':4,'蛾':6}")
    player_b_aspects: Dict[str, int] = Field(..., description="玩家B各性相等级")


class DeckConfirmRequest(BaseModel):
    """确认牌库请求"""
    battle_id: str = Field(..., description="对战ID")
    player_a_deck: List[str] = Field(..., min_length=8, max_length=8, description="A的8张牌ID")
    player_b_deck: List[str] = Field(..., min_length=8, max_length=8, description="B的8张牌ID")


class InitFromBaseRequest(BaseModel):
    """从Base面板发起对战请求（只需玩家名，API自动查性相等级）"""
    base_token: str = Field(..., description="Base token")
    player_a_name: str = Field(..., description="玩家A名称")
    player_b_name: str = Field(..., description="玩家B名称")
    battle_id: str = Field(default="", description="对战ID（workflow传record_id）")


class ConfirmFromBaseRequest(BaseModel):
    """从Base确认牌库请求"""
    base_token: str = Field(..., description="Base token")
    battle_id: str = Field(..., description="对战ID")
    side: str = Field(..., description="玩家侧: a/b")


class WebhookPayload(BaseModel):
    """Base自动化webhook载荷"""
    event: str = Field(default="card_submitted", description="事件类型")
    base_token: str = Field(..., description="触发Base的token")
    table_id: str = Field(default="", description="触发的表ID")
    record_id: str = Field(default="", description="触发的记录ID")
    battle_id: str = Field(default="", description="对战ID")
    round_number: int = Field(default=0, description="回合编号")
    selected_card: str = Field(default="", description="选择的卡牌ID")
    player_name: str = Field(default="", description="玩家名称")
    player_side: str = Field(default="a", description="玩家侧: a/b")


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
