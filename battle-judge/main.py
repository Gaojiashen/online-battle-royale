"""
密教模拟器S2 战斗裁判 — FastAPI 入口
部署于飞书妙搭 (Spark/Miaoda)
"""
import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

# 确保当前目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models import (
    BattleInitRequest, BattleInitResponse,
    DeckConfirmRequest, DeckConfirmResponse,
    WebhookPayload, WebhookResponse,
    BattleStatusResponse, BattleHistoryResponse,
)
from battle_manager import BattleManager
from webhook_handler import WebhookHandler
from card_library import ALL_CARDS, print_stats

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
