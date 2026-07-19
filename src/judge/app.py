"""
密教模拟器S2 战斗裁判 — FastAPI 入口
部署于 Render.com
"""
import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import asyncpg

from engine.card_library import ALL_CARDS, print_stats
from engine.battle_manager import BattleManager
from integration.event_bus import AsyncEventBus
from integration.event_log import EventLog
from integration.snapshot_store import SnapshotStore
from integration.dead_letter import DeadLetterQueue
from integration.websocket_manager import WebSocketManager
from integration.persistence_worker import PersistenceWorker
from integration.recovery import RecoveryManager
from integration.postgres_sync import PostgresSync
from integration.persistence_writer import PostgresWriter
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

    # ── Phase 2: 存储层 ──
    event_log = EventLog(data_dir="data/events")
    snapshot_store = SnapshotStore(data_dir="data/snapshots")
    dead_letter = DeadLetterQueue(
        path="data/dead_letters/dead_letters.jsonl"
    )

    # ── Phase 3: WebSocket 实时推送 ──
    ws_manager = WebSocketManager()
    from routes.websocket import set_ws_manager
    set_ws_manager(ws_manager)

    # ── Phase 1: EventBus + PersistenceWorker ──
    event_bus = AsyncEventBus(
        queue_size=256,
        event_log=event_log,
        dead_letter_queue=dead_letter,
        websocket_manager=ws_manager,
    )
    battle_manager = BattleManager(event_bus=event_bus)

    # ── Phase 5.1: PostgreSQL 持久化层 ──
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    print(f"DATABASE_URL configured: {bool(DATABASE_URL)}")
    db_pool = None
    postgres_sync = PostgresSync(pool=None)
    if DATABASE_URL:
        try:
            db_pool = await asyncpg.create_pool(
                dsn=DATABASE_URL,
                min_size=2,
                max_size=10,
            )
            postgres_sync = PostgresSync(pool=db_pool)
            print(f"Postgres pool ready: True (2–10)")
        except Exception as e:
            print(f"Postgres pool ready: False ({e})")
    else:
        print("Postgres pool ready: False (no DATABASE_URL)")

    # 注入到 player_service 读取层
    from services.player_service import set_pg_read_pool
    set_pg_read_pool(db_pool)
    print(f"player_service pool injected: {db_pool is not None}")

    # ── 自动 migration（空库初始化）──
    if db_pool:
        try:
            tables = await db_pool.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            existing = {r["table_name"] for r in tables}
            required = {"players", "battles", "battle_players",
                        "battle_rounds", "battle_submissions"}
            if not required.issubset(existing):
                import os as _os
                migration_path = _os.path.join(
                    _os.path.dirname(_os.path.abspath(__file__)),
                    "migrations", "001_init.sql",
                )
                with open(migration_path, encoding="utf-8") as f:
                    sql = f.read()
                await db_pool.execute(sql)
                print(f"Migration executed: {len(required)} tables created")
            else:
                print(f"Migration skipped: all {len(required)} tables exist")
        except Exception as e:
            print(f"Migration failed: {e}")

    # ── PersistenceWorker → PostgresWriter → PostgreSQL ──
    writer = PostgresWriter(postgres_sync=postgres_sync)
    persistence_worker = PersistenceWorker(
        writer,
        snapshot_store=snapshot_store,
        battle_manager=battle_manager,
    )
    persistence_worker.register(event_bus)

    # ── Phase 2: 崩溃恢复（在 HTTP 服务启动前执行）──
    recovery = RecoveryManager(battle_manager, snapshot_store, event_log)
    recovered = recovery.recover_all_sessions()
    if recovered > 0:
        print(f"已恢复 {recovered} 个对战")

    # ── 启动后台消费者 ──
    await event_bus.start()

    # ── 挂载到 app.state ──
    webhook_handler = WebhookHandler(battle_manager)
    app.state.battle_manager = battle_manager
    app.state.webhook_handler = webhook_handler
    app.state.ws_manager = ws_manager
    app.state.event_bus = event_bus
    app.state.db_pool = db_pool
    app.state.postgres_sync = postgres_sync

    yield

    # ── 优雅关闭 ──
    set_pg_read_pool(None)
    if db_pool:
        await db_pool.close()
        print("PostgreSQL 连接池已关闭")
    await event_bus.stop()
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

    # 挂载静态文件
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # 注册路由
    from routes.battle import router as battle_router
    from routes.judge_panel import router as judge_router
    from routes.player_client import router as player_router
    from routes.websocket import router as websocket_router
    from routes.admin import router as admin_router

    app.include_router(battle_router)
    app.include_router(judge_router)
    app.include_router(player_router)
    app.include_router(websocket_router)
    app.include_router(admin_router)

    return app


app = create_app()


# ════════════════════════════════════════════════════
# 基础端点
# ════════════════════════════════════════════════════

@app.get("/")
async def root():
    return {"ok": True, "service": "密教模拟器S2-战斗裁判", "cards": len(ALL_CARDS)}


@app.get("/health")
async def health(request: Request):
    """健康检查 — 包含运行时指标"""
    bm = request.app.state.battle_manager
    ws = request.app.state.ws_manager
    bus = request.app.state.event_bus

    # 统计活跃对战（非 finished）
    active_count = sum(
        1 for s in bm._battles.values() if s.state != "finished"
    )

    # 统计 WebSocket 连接总数
    ws_total = sum(len(conns) for conns in ws._connections.values())

    # 事件队列大小
    queue_size = getattr(bus, '_queue', None)
    queue_count = queue_size.qsize() if queue_size else 0

    return {
        "ok": True,
        "status": "healthy",
        "active_battles": active_count,
        "ws_connections": ws_total,
        "event_queue_size": queue_count,
    }


# ════════════════════════════════════════════════════
# 启动
# ════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port,
                ws_ping_interval=20, ws_ping_timeout=10)
