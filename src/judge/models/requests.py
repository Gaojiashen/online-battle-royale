"""
Pydantic 请求模型 — API 请求
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional


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
