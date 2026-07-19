"""
玩家客户端 — 请求模型
"""
from pydantic import BaseModel, Field
from typing import List


class SelectDeckRequest(BaseModel):
    """玩家确认 8 张牌选择"""
    player_name: str = Field(..., description="玩家名称")
    battle_id: str = Field(..., description="对战ID")
    card_ids: List[str] = Field(
        ..., min_length=1, max_length=8,
        description="选中的卡牌（1-8张）"
    )


class SubmitCardRequest(BaseModel):
    """玩家提交本回合出牌"""
    player_name: str = Field(..., description="玩家名称")
    battle_id: str = Field(..., description="对战ID")
    round_number: int = Field(..., description="回合编号")
    card_id: str = Field(..., description="选择的卡牌ID")
