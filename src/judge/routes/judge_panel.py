"""
法官操作面板 — HTML页面 + pending API
"""
import os
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# 读取HTML模板
_TEMPLATE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HTML_PATH = os.path.join(_TEMPLATE_DIR, "templates", "judge_panel.html")

with open(_HTML_PATH, "r", encoding="utf-8") as f:
    JUDGE_HTML = f.read()


@router.get("/judge", response_class=HTMLResponse)
async def judge_panel():
    """法官操作面板 — 处理待发起对战"""
    return HTMLResponse(JUDGE_HTML)


@router.get("/api/judge/pending")
async def judge_pending(request: Request):
    """读取待发起的对战（state='initialized'）。"""
    pool = request.app.state.db_pool
    if pool is None:
        return {"ok": True, "records": []}

    try:
        rows = await pool.fetch(
            "SELECT battle_id, player_a_name, player_b_name "
            "FROM battles WHERE state = '已初始化' "
            "ORDER BY created_at DESC"
        )
        pending = [
            {
                "record_id": row["battle_id"],
                "player_a": row["player_a_name"],
                "player_b": row["player_b_name"],
            }
            for row in rows
        ]
        return {"ok": True, "records": pending}
    except Exception as e:
        logger.error(f"judge_pending failed: {e}")
        return {"ok": False, "error": str(e)}
