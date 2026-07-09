"""
密教模拟器S2 战斗裁判 — FastAPI 入口
部署于 Render.com
"""
import os
import sys
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from models import (
    BattleInitRequest, BattleInitResponse,
    DeckConfirmRequest, DeckConfirmResponse,
    InitFromBaseRequest, ConfirmFromBaseRequest,
    WebhookPayload, WebhookResponse,
    BattleStatusResponse, BattleHistoryResponse,
)
from battle_manager import BattleManager
from webhook_handler import WebhookHandler
from base_sync import base_sync
from feishu_client import feishu_client
from card_library import ALL_CARDS, print_stats, get_available_cards

# ════════════════════════════════════════════════════
# 全局状态
# ════════════════════════════════════════════════════

battle_manager: BattleManager = None
webhook_handler: WebhookHandler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    global battle_manager, webhook_handler

    print("=" * 50)
    print("密教模拟器S2 战斗裁判 启动中...")
    print_stats()
    print("=" * 50)

    battle_manager = BattleManager()
    webhook_handler = WebhookHandler(battle_manager)

    yield

    print("战斗裁判已关闭")


app = FastAPI(
    title="密教模拟器S2-战斗裁判",
    description="回合制PvP战斗AI法官",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ════════════════════════════════════════════════════
# API 端点
# ════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"ok": True, "service": "密教模拟器S2-战斗裁判", "cards": len(ALL_CARDS)}


@app.get("/health")
async def health():
    return {"ok": True, "status": "healthy"}


@app.post("/api/battle/init", response_model=BattleInitResponse)
async def battle_init(req: BattleInitRequest):
    """
    法官初始化对战：
    - 计算双方可用牌库
    - 创建对战会话
    - 返回 battle_id
    """
    try:
        result = await battle_manager.init_battle(req)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/battle/init-from-base")
async def battle_init_from_base(req: InitFromBaseRequest):
    """
    从Base法官面板发起对战（聚合：查性相 + 初始化 + 写回Base所有表）
    1. 从Base「玩家」表查询双方性相等级
    2. 内部调用 battle_init
    3. 将可用牌写入「玩家可用牌」表
    """
    # 1. 从Base查询玩家性相等级
    ASPECT_KEYS = ["灯", "蛾", "刃", "铸", "冬", "心"]
    player_a_aspects = {}
    player_b_aspects = {}

    try:
        records = await feishu_client.list_records(req.base_token, "tbl4KaRcfiz1pZq1")
        for r in records:
            fields = r.get("fields", {})
            name = fields.get("玩家名称", "")
            if name == req.player_a_name:
                player_a_aspects = {k: int(fields.get(k, 0) or 0) for k in ASPECT_KEYS}
            elif name == req.player_b_name:
                player_b_aspects = {k: int(fields.get(k, 0) or 0) for k in ASPECT_KEYS}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"查询玩家数据失败: {e}")

    if not player_a_aspects:
        raise HTTPException(status_code=404, detail=f"玩家 '{req.player_a_name}' 不存在")
    if not player_b_aspects:
        raise HTTPException(status_code=404, detail=f"玩家 '{req.player_b_name}' 不存在")

    # 2. 转换为标准 init 请求
    init_req = BattleInitRequest(
        player_a_base_token=req.base_token,
        player_b_base_token=req.base_token,
        player_a_name=req.player_a_name,
        player_b_name=req.player_b_name,
        player_a_aspects=player_a_aspects,
        player_b_aspects=player_b_aspects,
    )
    result = await battle_manager.init_battle(init_req)

    # 3. 写入可用牌到Base
    a_cards = [{"id": c.id, "name": c.name, "category": c.category, "aspect": c.aspect}
               for c in get_available_cards(player_a_aspects)]
    b_cards = [{"id": c.id, "name": c.name, "category": c.category, "aspect": c.aspect}
               for c in get_available_cards(player_b_aspects)]

    import asyncio
    asyncio.create_task(base_sync.sync_available_cards(
        battle_id=result.battle_id, side="A",
        player_name=req.player_a_name, cards=a_cards,
    ))
    asyncio.create_task(base_sync.sync_available_cards(
        battle_id=result.battle_id, side="B",
        player_name=req.player_b_name, cards=b_cards,
    ))

    # 4. 更新法官面板的记录，写入对战ID
    if req.battle_id:
        asyncio.create_task(_update_judge_panel(req.base_token, req.battle_id, result.battle_id))

    return {
        "ok": True,
        "battle_id": result.battle_id,
        "player_a_name": req.player_a_name,
        "player_b_name": req.player_b_name,
        "player_a_aspects": player_a_aspects,
        "player_b_aspects": player_b_aspects,
        "player_a_available_count": len(a_cards),
        "player_b_available_count": len(b_cards),
    }


async def _update_judge_panel(base_token: str, record_id: str, battle_id: str):
    """回写法官面板记录的对战ID和状态"""
    try:
        await feishu_client.update_record(
            base_token, "tblbheflCQ2wTgml", record_id,
            {"对战ID": battle_id, "状态": "已发起"},
        )
    except Exception as e:
        logger.error(f"更新法官面板失败: {e}")


@app.post("/api/battle/confirm-from-base")
async def battle_confirm_from_base(req: ConfirmFromBaseRequest):
    """
    玩家在Base确认牌库后调用（由workflow触发）
    读取玩家战斗状态中的牌位1-8，确认牌库
    """
    import asyncio

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
        session = battle_manager._battles.get(req.battle_id)
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
                    result = await battle_manager.confirm_deck(confirm_req)
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


@app.post("/api/battle/confirm-deck", response_model=DeckConfirmResponse)
async def battle_confirm_deck(req: DeckConfirmRequest):
    """
    法官确认双方8张牌已选好
    - 锁定牌库
    - 初始化HP=20
    - 开始第1回合
    """
    try:
        result = await battle_manager.confirm_deck(req)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/battle/webhook", response_model=WebhookResponse)
async def battle_webhook(req: WebhookPayload):
    """
    接收Base自动化触发的选牌提交
    """
    try:
        result = await webhook_handler.handle(req)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/battle/{battle_id}/status", response_model=BattleStatusResponse)
async def battle_status(battle_id: str):
    """
    查询对战状态
    """
    try:
        result = battle_manager.get_status(battle_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"对战不存在: {battle_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/battle/{battle_id}/history", response_model=BattleHistoryResponse)
async def battle_history(battle_id: str):
    """
    获取完整战斗记录
    """
    try:
        result = battle_manager.get_history(battle_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"对战不存在: {battle_id}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ════════════════════════════════════════════════════
# 启动
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
