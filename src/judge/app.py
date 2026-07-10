"""
密教模拟器S2 战斗裁判 — FastAPI 入口
部署于 Render.com
"""
import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.card_library import ALL_CARDS, print_stats
from engine.battle_manager import BattleManager
from routes.webhook import WebhookHandler

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════
# 应用工厂
# ════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    print("=" * 50)
    print("密教模拟器S2 战斗裁判 启动中...")
    print_stats()
    print("=" * 50)

    battle_manager = BattleManager()
    webhook_handler = WebhookHandler(battle_manager)

    # 挂载到 app.state 供路由访问
    app.state.battle_manager = battle_manager
    app.state.webhook_handler = webhook_handler

    yield

    print("战斗裁判已关闭")


def create_app() -> FastAPI:
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

    # 注册路由
    from routes.battle import router as battle_router
    from routes.judge_panel import router as judge_router

    app.include_router(battle_router)
    app.include_router(judge_router)

    return app


app = create_app()


# ════════════════════════════════════════════════════
# 基础端点
# ════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"ok": True, "service": "密教模拟器S2-战斗裁判", "cards": len(ALL_CARDS)}


@app.get("/health")
async def health():
    return {"ok": True, "status": "healthy"}


# ════════════════════════════════════════════════════
# 启动
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
