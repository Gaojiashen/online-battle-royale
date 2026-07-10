"""
法官操作面板 — HTML页面 + pending API
"""
import os
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from integration.feishu_client import feishu_client

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
async def judge_pending():
    """读取法官面板中待发起的记录"""
    try:
        records = await feishu_client.list_records(
            "CB6XbtkLaafJnYsDL8RcHFpEnDg", "tblbheflCQ2wTgml"
        )
        pending = []
        for r in records:
            fields = r.get("fields", {})
            status = fields.get("状态", "")
            # 处理单选字段返回数组的情况
            if isinstance(status, list):
                status = status[0] if status else ""
            if status == "待发起":
                pending.append({
                    "record_id": r.get("record_id", ""),
                    "player_a": fields.get("玩家A", ""),
                    "player_b": fields.get("玩家B", ""),
                })
        return {"ok": True, "records": pending}
    except Exception as e:
        return {"ok": False, "error": str(e)}
