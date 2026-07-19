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
    法官初始化对战。
    如果未提供 aspects，则从 PostgreSQL players 表查询填充。
    """
    bm = request.app.state.battle_manager
    pool = request.app.state.db_pool

    # 如果 aspects 未提供，从 PG 查询
    if not req.player_a_aspects or not req.player_b_aspects:
        if pool is None:
            raise HTTPException(status_code=503, detail="数据库不可用")
        for name_key, attr_key in [
            (req.player_a_name, "player_a_aspects"),
            (req.player_b_name, "player_b_aspects"),
        ]:
            if not getattr(req, attr_key):
                row = await pool.fetchrow(
                    "SELECT lantern, moth, forge, winter, heart, blade "
                    "FROM players WHERE name = $1",
                    name_key,
                )
                if row:
                    setattr(req, attr_key, {
                        "灯": row["lantern"], "蛾": row["moth"],
                        "铸": row["forge"], "冬": row["winter"],
                        "心": row["heart"], "刃": row["blade"],
                    })
                else:
                    # 新玩家 — 默认性相等级 1
                    setattr(req, attr_key, {
                        "灯": 1, "蛾": 1, "铸": 1, "冬": 1, "心": 1, "刃": 1,
                    })

    try:
        result = await bm.init_battle(req)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
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
