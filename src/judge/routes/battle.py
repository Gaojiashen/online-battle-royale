"""
对战API端点 — init / confirm / webhook / status / history
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Request

from models import (
    BattleInitRequest, BattleInitResponse,
    DeckConfirmRequest, DeckConfirmResponse,
    WebhookPayload, WebhookResponse,
    BattleStatusResponse, BattleHistoryResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/api/battle/init", response_model=BattleInitResponse)
async def battle_init(req: BattleInitRequest, request: Request):
    """
    法官初始化对战：
    - 计算双方可用牌库
    - 创建对战会话
    - 返回 battle_id
    """
    bm = request.app.state.battle_manager
    try:
        result = await bm.init_battle(req)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/battle/init-from-base")
@router.post("/api/battle/confirm-deck", response_model=DeckConfirmResponse)
async def battle_confirm_deck(req: DeckConfirmRequest, request: Request):
    """
    法官确认双方8张牌已选好
    - 锁定牌库
    - 初始化HP=20
    - 开始第1回合
    """
    bm = request.app.state.battle_manager
    try:
        result = await bm.confirm_deck(req)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/battle/webhook", response_model=WebhookResponse)
async def battle_webhook(req: WebhookPayload, request: Request):
    """
    接收Base自动化触发的选牌提交
    """
    wh = request.app.state.webhook_handler
    try:
        result = await wh.handle(req)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/battle/{battle_id}/status", response_model=BattleStatusResponse)
async def battle_status(battle_id: str, request: Request):
    """
    查询对战状态
    """
    bm = request.app.state.battle_manager
    try:
        result = bm.get_status(battle_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"对战不存在: {battle_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/battle/{battle_id}/history", response_model=BattleHistoryResponse)
async def battle_history(battle_id: str, request: Request):
    """
    获取完整战斗记录
    """
    bm = request.app.state.battle_manager
    try:
        result = bm.get_history(battle_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"对战不存在: {battle_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
