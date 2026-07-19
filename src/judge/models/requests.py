"""
Pydantic 请求模型 — API 请求
"""
from pydantic import BaseModel, Field
from typing import Dict, List, Optional


# ════════════════════════════════════════════════════
# 请求模型
# ════════════════════════════════════════════════════

class BattleInitRequest(BaseModel):
    """创建对战请求 — aspects 可选，未提供时由后端从 players 表查询。"""
    player_a_name: str = Field(..., description="玩家A名称")
    player_b_name: str = Field(..., description="玩家B名称")
    player_a_base_token: str = Field(default="", description="玩家A Base token（已废弃，保留兼容）")
    player_b_base_token: str = Field(default="", description="玩家B Base token（已废弃，保留兼容）")
    player_a_aspects: Dict[str, int] = Field(default_factory=dict, description="玩家A性相等级")
    player_b_aspects: Dict[str, int] = Field(default_factory=dict, description="玩家B性相等级")


class DeckConfirmRequest(BaseModel):
    """确认牌库请求"""
    battle_id: str = Field(..., description="对战ID")
    player_a_deck: List[str] = Field(..., min_length=1, max_length=8, description="A的牌库（1-8张）")
    player_b_deck: List[str] = Field(..., min_length=1, max_length=8, description="B的牌库（1-8张）")


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
