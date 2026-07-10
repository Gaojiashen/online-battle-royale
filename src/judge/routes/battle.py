"""
对战API端点 — init / confirm / webhook / status / history
"""
import logging
from fastapi import APIRouter, HTTPException, Request

from models import (
    BattleInitRequest, BattleInitResponse,
    DeckConfirmRequest, DeckConfirmResponse,
    InitFromBaseRequest, ConfirmFromBaseRequest,
    WebhookPayload, WebhookResponse,
    BattleStatusResponse, BattleHistoryResponse,
)
from integration.base_sync import base_sync

logger = logging.getLogger(__name__)

router = APIRouter()


# ════════════════════════════════════════════════════
# 辅助函数
# ════════════════════════════════════════════════════

async def _update_judge_panel(base_token: str, record_id: str, battle_id: str):
    """回写法官面板记录的对战ID和状态"""
    from integration.feishu_client import feishu_client
    try:
        await feishu_client.update_record(
            base_token, "tblbheflCQ2wTgml", record_id,
            {"对战ID": battle_id, "状态": "已发起"},
        )
    except Exception as e:
        logger.error(f"更新法官面板失败: {e}")


# ════════════════════════════════════════════════════
# 对战端点
# ════════════════════════════════════════════════════

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
async def battle_init_from_base(req: InitFromBaseRequest, request: Request):
    """
    从Base法官面板发起对战（聚合：查性相 + 初始化 + 写回Base所有表）
    1. 从Base「玩家」表查询双方性相等级
    2. 内部调用 battle_init
    3. 将可用牌写入「玩家可用牌」表
    """
    import asyncio
    from integration.feishu_client import feishu_client

    bm = request.app.state.battle_manager

    # 1. 从Base查性相
    try:
        player_records = await feishu_client.list_records(
            req.base_token, "tbl1NnOpplq3x7Rg"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取玩家表失败: {e}")

    aspects_a = {}
    aspects_b = {}
    for r in player_records:
        fields = r.get("fields", {})
        name = fields.get("名称", "")
        if name == req.player_a_name:
            aspects_a = {
                k: int(v) for k, v in fields.items()
                if k in ("灯", "蛾", "铸", "冬", "心", "刃")
            }
        elif name == req.player_b_name:
            aspects_b = {
                k: int(v) for k, v in fields.items()
                if k in ("灯", "蛾", "铸", "冬", "心", "刃")
            }

    if not aspects_a:
        raise HTTPException(status_code=400, detail=f"未找到玩家A: {req.player_a_name}")
    if not aspects_b:
        raise HTTPException(status_code=400, detail=f"未找到玩家B: {req.player_b_name}")

    # 2. 内部初始化
    internal_req = BattleInitRequest(
        player_a_base_token=req.base_token,
        player_b_base_token=req.base_token,
        player_a_name=req.player_a_name,
        player_b_name=req.player_b_name,
        player_a_aspects=aspects_a,
        player_b_aspects=aspects_b,
    )
    try:
        result = await bm.init_battle(internal_req)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"初始化对战失败: {e}")

    # 3. 写入Base
    try:
        await base_sync.sync_battle_init(result.battle_id, req, result,
                                          aspects_a, aspects_b)
    except Exception as e:
        logger.error(f"Base同步失败(非阻塞): {e}")

    # 4. 回写法官面板
    if req.battle_id:
        asyncio.create_task(_update_judge_panel(req.base_token, req.battle_id, result.battle_id))

    return {
        "ok": True,
        "battle_id": result.battle_id,
        "player_a_available_count": len(result.player_a_available),
        "player_b_available_count": len(result.player_b_available),
        "message": result.message,
    }


@router.post("/api/battle/confirm-from-base")
async def battle_confirm_from_base(req: ConfirmFromBaseRequest, request: Request):
    """
    玩家在Base确认牌库后调用（由workflow触发）
    读取玩家战斗状态中的牌位1-8，确认牌库
    """
    import asyncio
    from integration.feishu_client import feishu_client

    bm = request.app.state.battle_manager

    # 从Base读取该玩家在牌位1-8填写的卡牌
    cards = []
    try:
        records = await feishu_client.list_records(
            req.base_token, "tblTNAkesS7WlJoR"
        )
        for r in records:
            fields = r.get("fields", {})
            if fields.get("对战ID") == req.battle_id and fields.get("玩家侧") == req.side.upper():
                for i in range(1, 9):
                    card_id = fields.get(f"牌位{i}", "")
                    if card_id:
                        cards.append(card_id)
                break
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"读取牌位失败: {e}")

    if len(cards) != 8:
        return {"ok": False, "message": f"需要8张牌，当前只选了{len(cards)}张"}

    # 更新Base中的确认标记
    asyncio.create_task(base_sync.sync_deck_confirmed(
        battle_id=req.battle_id, side=req.side.upper(), deck=cards,
    ))

    # 检查双方是否都确认了
    both_ready = await base_sync.check_both_decks_confirmed(req.battle_id)

    if both_ready:
        # 双方都确认了，调用confirm_deck
        session = bm._battles.get(req.battle_id)
        if session:
            a_cards = []
            b_cards = []
            try:
                records = await feishu_client.list_records(
                    req.base_token, "tblTNAkesS7WlJoR"
                )
                for r in records:
                    fields = r.get("fields", {})
                    if fields.get("对战ID") == req.battle_id:
                        side_cards = []
                        for i in range(1, 9):
                            cid = fields.get(f"牌位{i}", "")
                            if cid:
                                side_cards.append(cid)
                        if fields.get("玩家侧") == "A":
                            a_cards = side_cards
                        else:
                            b_cards = side_cards

                if len(a_cards) == 8 and len(b_cards) == 8:
                    confirm_req = DeckConfirmRequest(
                        battle_id=req.battle_id,
                        player_a_deck=a_cards,
                        player_b_deck=b_cards,
                    )
                    result = await bm.confirm_deck(confirm_req)
                    return {
                        "ok": True,
                        "battle_id": req.battle_id,
                        "state": "in_progress",
                        "message": "双方牌库已确认，对战开始！",
                    }
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"确认牌库失败: {e}")

    return {
        "ok": True,
        "battle_id": req.battle_id,
        "status": "waiting" if not both_ready else "confirmed",
        "message": f"{'双方' if both_ready else '等待对手'}已确认" if not both_ready else "对战开始",
    }


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
