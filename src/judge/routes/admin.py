"""
Admin Panel API — 玩家管理 + 数据库诊断
"""
import json
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# 读取 HTML 模板
import os
_TEMPLATE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_TEMPLATE_DIR, "templates", "admin.html")
with open(_HTML_PATH, "r", encoding="utf-8") as f:
    ADMIN_HTML = f.read()

REQUIRED_TABLES = [
    "players", "battles", "battle_players",
    "battle_rounds", "battle_submissions",
]


class CreatePlayerRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


# ════════════════════════════════════════════════════
# HTML 页面
# ════════════════════════════════════════════════════

@router.get("/admin", response_class=HTMLResponse)
async def admin_page():
    return HTMLResponse(ADMIN_HTML)


# ════════════════════════════════════════════════════
# 玩家管理
# ════════════════════════════════════════════════════

@router.get("/api/admin/players")
async def list_players(request: Request):
    pool = request.app.state.db_pool
    if pool is None:
        return {"ok": False, "players": [], "error": "数据库不可用"}

    rows = await pool.fetch(
        "SELECT id, name, lantern, moth, forge, winter, heart, blade, "
        "game_hp, created_at FROM players ORDER BY id"
    )
    players = []
    for r in rows:
        players.append({
            "id": r["id"],
            "name": r["name"],
            "aspects": {
                "灯": r["lantern"], "蛾": r["moth"],
                "铸": r["forge"], "冬": r["winter"],
                "心": r["heart"], "刃": r["blade"],
            },
            "game_hp": r["game_hp"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else "",
        })
    return {"ok": True, "players": players}


@router.post("/api/admin/players")
async def create_player(req: CreatePlayerRequest, request: Request):
    pool = request.app.state.db_pool
    if pool is None:
        raise HTTPException(status_code=503, detail="数据库不可用")

    try:
        await pool.execute(
            "INSERT INTO players (name) VALUES ($1)",
            req.name,
        )
        row = await pool.fetchrow(
            "SELECT id, name, created_at FROM players WHERE name = $1",
            req.name,
        )
        return {
            "ok": True,
            "player": {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            },
        }
    except Exception as e:
        # 唯一键冲突
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=409, detail=f"玩家 '{req.name}' 已存在")
        logger.exception("create_player failed")
        raise HTTPException(status_code=400, detail=str(e))


# ════════════════════════════════════════════════════
# 数据库诊断
# ════════════════════════════════════════════════════

@router.get("/api/admin/db-status")
async def db_status(request: Request):
    pool = request.app.state.db_pool
    if pool is None:
        return {
            "database_connected": False,
            "tables": [],
            "missing_tables": REQUIRED_TABLES,
            "row_counts": {},
        }

    try:
        rows = await pool.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' ORDER BY table_name"
        )
        existing = [r["table_name"] for r in rows]
        missing = [t for t in REQUIRED_TABLES if t not in existing]

        row_counts = {}
        for t in existing:
            cnt = await pool.fetchval(f"SELECT COUNT(*) FROM {t}")
            row_counts[t] = cnt

        return {
            "database_connected": True,
            "tables": existing,
            "missing_tables": missing,
            "row_counts": row_counts,
        }
    except Exception as e:
        return {
            "database_connected": True,
            "tables": [],
            "missing_tables": REQUIRED_TABLES,
            "row_counts": {},
            "error": str(e),
        }
