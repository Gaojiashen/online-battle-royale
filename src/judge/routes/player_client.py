"""
玩家客户端 — HTML 页面 + API 端点
"""
import os
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from models import SelectDeckRequest, SubmitCardRequest
from services import player_service

logger = logging.getLogger(__name__)

router = APIRouter()

# 读取 HTML 模板
_TEMPLATE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_TEMPLATE_DIR, "templates", "player_client.html")
with open(_HTML_PATH, "r", encoding="utf-8") as f:
    PLAYER_HTML = f.read()


# ════════════════════════════════════════════════════
# HTML 页面
# ════════════════════════════════════════════════════

@router.get("/player", response_class=HTMLResponse)
async def player_page():
    """玩家战斗客户端页面"""
    return HTMLResponse(PLAYER_HTML)


# ════════════════════════════════════════════════════
# 玩家 API
# ════════════════════════════════════════════════════

@router.get("/api/player/lookup")
async def player_lookup(name: str = ""):
    """查找玩家信息"""
    if not name:
        return {"ok": False, "message": "请提供玩家名称"}
    return await player_service.lookup_player(name)


@router.get("/api/player/{name}/battle")
async def player_battle(name: str, request: Request):
    """获取玩家视角的战斗状态"""
    bm = request.app.state.battle_manager
    result = await player_service.get_player_battle(name, bm)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message", ""))
    return result


@router.get("/api/player/{name}/available-cards")
async def player_available_cards(name: str):
    """获取玩家可用卡牌列表"""
    result = await player_service.get_available_cards(name)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message", ""))
    return result


@router.post("/api/player/select-deck")
async def player_select_deck(req: SelectDeckRequest, request: Request):
    """确认 8 张牌选择"""
    bm = request.app.state.battle_manager
    result = await player_service.select_deck(
        req.player_name, req.battle_id, req.card_ids, bm,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message", ""))
    return result


@router.post("/api/player/submit-card")
async def player_submit_card(req: SubmitCardRequest, request: Request):
    """提交本回合出牌"""
    bm = request.app.state.battle_manager
    side = await player_service.get_player_side(req.player_name)
    if not side:
        raise HTTPException(status_code=400, detail="无法确定玩家侧")
    result = player_service.submit_card(req.battle_id, side.lower(), req.card_id, bm)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message", ""))
    return result


@router.get("/api/player/{name}/battle-logs")
async def player_battle_logs(name: str):
    """获取玩家视角的战斗日志"""
    result = await player_service.get_battle_logs(name)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("message", ""))
    return result
