"""
隐秘爱丁堡 · NPC剧情线管理工具
FastAPI + SQLite + WebSocket 实时同步
"""
import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from database import (
    get_db, init_db, fetch_all_npcs, fetch_npc, fetch_nodes, fetch_options,
    fetch_events, log_event, get_nav_data, fetch_npc_connections, fetch_all_connections,
    fetch_players, fetch_player, fetch_player_actions, fetch_stats,
    fetch_location, fetch_location_by_name, fetch_location_by_region_num,
    fetch_connected_locations, fetch_npcs_at_location_by_regions, fetch_all_locations,
    fetch_npcs_at_location_filtered, check_node_availability,
    get_player_time_info, advance_game_time,
    fetch_search_pool, fetch_item, fetch_random_lore, add_player_item, fetch_player_inventory, add_player_gold,
)

# ── WebSocket 连接管理器 ────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, event: str, data: dict):
        payload = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        stale = []
        for ws in self.active:
            try:
                await ws.send_text(payload)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


manager = ConnectionManager()


# ── 生命周期 ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


# ── App ─────────────────────────────────────────────────────
app = FastAPI(title="隐秘爱丁堡 · NPC管理工具", lifespan=lifespan)

from jinja2 import Environment, FileSystemLoader
_jinja_env = Environment(loader=FileSystemLoader("templates"))

def render(name: str, **ctx) -> str:
    tpl = _jinja_env.get_template(name)
    return tpl.render(**ctx)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ── 辅助函数 ────────────────────────────────────────────────
def _d(row):
    """Convert sqlite Row to dict if needed"""
    return dict(row) if row and not isinstance(row, dict) else row

def _ds(rows):
    """Convert list of sqlite Rows to list of dicts"""
    return [dict(r) if not isinstance(r, dict) else r for r in rows]

def lock_label(lock_status: str) -> str:
    labels = {"无主": "🔓 无主", "锁定": "🔒 锁定", "完结": "✅ 完结", "终结": "💀 终结"}
    return labels.get(lock_status, lock_status)

def aspect_tag(aspect: str) -> str:
    tags = {"灯":"🔆","蛾":"🦋","刃":"⚔️","铸":"🔨","冬":"❄️","心":"💓","?":"❓"}
    return tags.get(aspect, "")

def status_label(s: str) -> str:
    labels = {"alive":"存活","injured":"受伤","dead":"死亡","missing":"失踪"}
    return labels.get(s, s)


# ── 页面路由 ───────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    tier = request.query_params.get("tier")
    aspect = request.query_params.get("aspect")
    npcs = _ds(fetch_all_npcs(tier=tier, aspect=aspect))
    events = _ds(fetch_events())
    stats = fetch_stats()
    nav = get_nav_data()
    for npc in npcs:
        npc["lock_label"] = lock_label(npc["lock_status"])
        npc["aspect_tag"] = aspect_tag(npc["aspect"])
    return HTMLResponse(render(
        "index.html", request=request, npcs=npcs, events=events,
        stats=stats, nav=nav, current_tier=tier, current_aspect=aspect))


@app.get("/npc/{npc_id}", response_class=HTMLResponse)
async def npc_detail(request: Request, npc_id: int):
    npc = _d(fetch_npc(npc_id))
    if not npc:
        return HTMLResponse("NPC not found", status_code=404)
    npc["lock_label"] = lock_label(npc["lock_status"])
    npc["aspect_tag"] = aspect_tag(npc["aspect"])
    nodes = _ds(fetch_nodes(npc_id))
    events = _ds(fetch_events(npc_id))
    connections = _ds(fetch_npc_connections(npc_id))
    nav = get_nav_data()

    current_options = []
    next_node_num = None
    last_completed_num = None
    for n in nodes:
        if n["completed"]:
            last_completed_num = n["node_number"]
        elif next_node_num is None:
            next_node_num = n["node_number"]
            current_options = fetch_options(n["id"])

    return HTMLResponse(render(
        "npc_detail.html", request=request, npc=npc, nodes=nodes,
        events=events, next_node_num=next_node_num,
        last_completed_num=last_completed_num,
        current_options=current_options,
        connections=connections, nav=nav,
        lock_statuses=["无主", "锁定", "完结", "终结"],
        npc_statuses=["alive", "injured", "dead", "missing"],
    ))


@app.get("/players", response_class=HTMLResponse)
async def players_page(request: Request):
    players = _ds(fetch_players())
    nav = get_nav_data()
    npcs = _ds(fetch_all_npcs())
    # 建立玩家->锁定NPC的映射
    for p in players:
        p["locked_npcs"] = [n for n in npcs if n["locked_player"] == p["name"]]
    return HTMLResponse(render(
        "players.html", request=request, players=players, nav=nav))


@app.get("/player/{player_id}", response_class=HTMLResponse)
async def player_detail(request: Request, player_id: int):
    player = _d(fetch_player(player_id))
    if not player:
        return HTMLResponse("Player not found", status_code=404)
    actions = _ds(fetch_player_actions(player_id))
    nav = get_nav_data()
    npcs = _ds(fetch_all_npcs())
    player["locked_npcs"] = [n for n in npcs if n["locked_player"] == player["name"]]
    return HTMLResponse(render(
        "player_detail.html", request=request, player=player,
        actions=actions, nav=nav))


@app.get("/connections", response_class=HTMLResponse)
async def connections_page(request: Request):
    connections = fetch_all_connections()
    nav = get_nav_data()
    return HTMLResponse(render(
        "connections.html", request=request, connections=connections, nav=nav))


# ── JSON 安全读取 ──────────────────────────────────────────
async def _json_body(request: Request) -> dict:
    raw = await request.body()
    try:
        return json.loads(raw)
    except UnicodeDecodeError:
        return json.loads(raw.decode("gbk"))


# ── API: NPC操作 ────────────────────────────────────────────
@app.post("/api/npc/{npc_id}/advance")
async def advance_node(npc_id: int, request: Request):
    data = await _json_body(request)
    player_name = data.get("player_name", "")
    db = get_db()
    npc = db.execute("SELECT * FROM npcs WHERE id = ?", (npc_id,)).fetchone()
    if not npc:
        db.close(); return {"ok": False, "error": "NPC不存在"}
    current = npc["current_node"]
    next_node = db.execute(
        "SELECT * FROM storyline_nodes WHERE npc_id=? AND node_number>? AND completed=0 "
        "ORDER BY node_number LIMIT 1", (npc_id, current)).fetchone()
    if not next_node:
        db.close(); return {"ok": False, "error": "没有可推进的节点"}
    new_node = next_node["node_number"]
    db.execute("UPDATE npcs SET current_node=? WHERE id=?", (new_node, npc_id))
    db.execute("UPDATE storyline_nodes SET completed=1,completed_by=? WHERE id=?",
               (player_name or None, next_node["id"]))
    db.commit(); db.close()
    desc = f"推进到节点{new_node}【{next_node['title']}】"
    if player_name: desc += f"（由 {player_name}）"
    log_event(npc_id, "node_advance", desc)
    await manager.broadcast("npc_update", {"npc_id": npc_id})
    return {"ok": True, "node": new_node, "title": next_node["title"]}


@app.post("/api/npc/{npc_id}/choose_option")
async def choose_option(npc_id: int, request: Request):
    data = await _json_body(request)
    option_key = data.get("option_key", "")
    db = get_db()
    cur_node = db.execute(
        "SELECT * FROM storyline_nodes WHERE npc_id=? AND completed=0 "
        "ORDER BY node_number LIMIT 1", (npc_id,)).fetchone()
    if not cur_node: db.close(); return {"ok": False, "error": "没有可进行的节点"}
    opt = db.execute(
        "SELECT * FROM node_options WHERE node_id=? AND option_key=?",
        (cur_node["id"], option_key)).fetchone()
    if not opt: db.close(); return {"ok": False, "error": f"选项{option_key}不存在"}
    db.execute("UPDATE storyline_nodes SET completed=1,completed_by=? WHERE id=?",
               ("[GM]", cur_node["id"]))
    db.execute("UPDATE npcs SET current_node=? WHERE id=?",
               (cur_node["node_number"], npc_id))
    db.commit(); db.close()
    log_event(npc_id, "node_complete",
              f"节点{cur_node['node_number']}【{cur_node['title']}】→ 选{option_key}")
    return {"ok": True, "option_key": option_key,
            "option_text": opt["option_text"], "result_text": opt["result_text"],
            "player_gain": opt["player_gain"] or "",
            "node_number": cur_node["node_number"], "node_title": cur_node["title"]}


@app.post("/api/npc/{npc_id}/rollback")
async def rollback_node(npc_id: int, request: Request):
    db = get_db()
    last = db.execute(
        "SELECT * FROM storyline_nodes WHERE npc_id=? AND completed=1 "
        "ORDER BY node_number DESC LIMIT 1", (npc_id,)).fetchone()
    if not last: db.close(); return {"ok": False, "error": "没有已完成的节点可回退"}
    prev = db.execute(
        "SELECT * FROM storyline_nodes WHERE npc_id=? AND completed=1 "
        "AND node_number<? ORDER BY node_number DESC LIMIT 1",
        (npc_id, last["node_number"])).fetchone()
    db.execute("UPDATE storyline_nodes SET completed=0,completed_by=NULL WHERE id=?",
               (last["id"],))
    db.execute("UPDATE npcs SET current_node=? WHERE id=?",
               (prev["node_number"] if prev else 0, npc_id))
    db.commit(); db.close()
    log_event(npc_id, "rollback", f"回退节点{last['node_number']}【{last['title']}】")
    return {"ok": True, "rolled_back_node": last["node_number"]}


@app.post("/api/npc/{npc_id}/lock")
async def update_lock(npc_id: int, request: Request):
    data = await _json_body(request)
    lock_status = data.get("lock_status")
    player_name = data.get("player_name", "")
    if lock_status not in ["无主", "锁定", "完结", "终结"]:
        return {"ok": False, "error": "无效的锁状态"}
    db = get_db()
    db.execute("UPDATE npcs SET lock_status=?,locked_player=? WHERE id=?",
               (lock_status, player_name or None, npc_id))
    db.commit(); db.close()
    desc = f"锁状态变更: {lock_status}"
    if player_name: desc += f"（{player_name}）"
    log_event(npc_id, "lock_change", desc)
    await manager.broadcast("npc_update", {"npc_id": npc_id})
    return {"ok": True}


@app.post("/api/npc/{npc_id}/status")
async def update_npc_status(npc_id: int, request: Request):
    data = await _json_body(request)
    status = data.get("status")
    if status not in ["alive", "injured", "dead", "missing"]:
        return {"ok": False, "error": "无效状态"}
    db = get_db()
    db.execute("UPDATE npcs SET status=? WHERE id=?", (status, npc_id))
    db.commit(); db.close()
    log_event(npc_id, "status_change", f"状态变更: {status_label(status)}")
    await manager.broadcast("npc_update", {"npc_id": npc_id})
    return {"ok": True}


@app.post("/api/npc/{npc_id}/note")
async def update_note(npc_id: int, request: Request):
    data = await _json_body(request)
    notes = data.get("notes", "")
    db = get_db()
    db.execute("UPDATE npcs SET notes=? WHERE id=?", (notes, npc_id))
    db.commit(); db.close()
    log_event(npc_id, "note", "笔记已更新")
    await manager.broadcast("npc_update", {"npc_id": npc_id})
    return {"ok": True}


@app.post("/api/npc/{npc_id}/location")
async def update_location(npc_id: int, request: Request):
    data = await _json_body(request)
    location = data.get("location", "")
    db = get_db()
    db.execute("UPDATE npcs SET location=? WHERE id=?", (location, npc_id))
    db.commit(); db.close()
    log_event(npc_id, "location_change", f"位置变更: {location}")
    await manager.broadcast("npc_update", {"npc_id": npc_id})
    return {"ok": True}


@app.get("/api/events")
async def get_events(npc_id: int = None):
    return fetch_events(npc_id)


@app.get("/api/npc/{npc_id}/connections")
async def get_connections(npc_id: int):
    return fetch_npc_connections(npc_id)


@app.get("/api/npc/{npc_id}/storyline-current")
async def get_storyline_current(npc_id: int, player_id: int = None):
    """获取NPC当前剧情节点和选项（用于玩家面板交互）。
    可选 player_id 参数用于校验地点和时间是否匹配。"""
    npc = _d(fetch_npc(npc_id))
    if not npc:
        return {"ok": False, "error": "NPC不存在"}
    nodes = _ds(fetch_nodes(npc_id))
    if not nodes or not npc.get("has_storyline"):
        return {"ok": False, "error": "该NPC没有剧情线"}

    # 找到当前待进行的节点
    current_node = None
    current_options = []
    next_node_num = None
    for n in nodes:
        if n["completed"]:
            continue
        elif next_node_num is None:
            next_node_num = n["node_number"]
            current_node = n
            current_options = fetch_options(n["id"])
            break

    if not current_node:
        return {"ok": False, "error": "该NPC剧情线已完结", "completed": True,
                "total_nodes": len(nodes)}

    # 如果提供了 player_id，进行地点和时间校验
    availability_warning = None
    if player_id:
        player = _d(fetch_player(player_id))
        if player and player.get("current_location"):
            avail = check_node_availability(
                npc_id, player["current_location"],
                player.get("game_time", 480)
            )
            if not avail["available"]:
                # 返回警告但不阻止（法官可能需要强制推进）
                availability_warning = avail["reason"]

    result = {
        "ok": True,
        "npc_id": npc_id,
        "npc_name": npc["name"],
        "node_id": current_node["id"],
        "node_number": current_node["node_number"],
        "node_title": current_node["title"],
        "location": current_node["location"],
        "description": current_node["description"],
        "hint": current_node["hint"],
        "total_nodes": len(nodes),
        "options": [dict(o) if not isinstance(o, dict) else o for o in current_options],
    }
    if availability_warning:
        result["warning"] = availability_warning
    return result


@app.post("/api/npc/{npc_id}/player-choose")
async def player_choose_option(npc_id: int, request: Request):
    """玩家面板中选择NPC剧情选项，推进时间并记录行动"""
    data = await _json_body(request)
    player_id = data.get("player_id")
    option_key = data.get("option_key", "")

    if not player_id:
        return {"ok": False, "error": "缺少player_id"}

    player = _d(fetch_player(player_id))
    if not player:
        return {"ok": False, "error": "玩家不存在"}

    db = get_db()
    # 找到当前未完成的节点
    cur_node = db.execute(
        "SELECT * FROM storyline_nodes WHERE npc_id=? AND completed=0 "
        "ORDER BY node_number LIMIT 1", (npc_id,)).fetchone()
    if not cur_node:
        db.close()
        return {"ok": False, "error": "没有可进行的节点"}

    opt = db.execute(
        "SELECT * FROM node_options WHERE node_id=? AND option_key=?",
        (cur_node["id"], option_key)).fetchone()
    if not opt:
        db.close()
        return {"ok": False, "error": f"选项{option_key}不存在"}

    # 标记节点完成
    player_name = player.get("name", "")
    db.execute("UPDATE storyline_nodes SET completed=1,completed_by=? WHERE id=?",
               (player_name, cur_node["id"]))
    db.execute("UPDATE npcs SET current_node=? WHERE id=?",
               (cur_node["node_number"], npc_id))
    db.commit()
    db.close()

    # 推进玩家时间（剧情节点交互：默认1h）
    cost_min = data.get("cost_minutes", 60)
    time_result = advance_game_time(player_id, cost_min)

    # 记录事件
    log_event(npc_id, "node_complete",
              f"节点{cur_node['node_number']}【{cur_node['title']}】→ 选{option_key}（玩家: {player_name}）")

    # 记录玩家行动日志
    _log_player_action(
        player_id, 0, "剧情",
        f"📜 与「{fetch_npc(npc_id)['name']}」剧情: 节点{cur_node['node_number']}【{cur_node['title']}】→ 选{option_key}",
        opt["result_text"], npc_id, player.get("current_location")
    )

    await manager.broadcast("npc_update", {"npc_id": npc_id})
    await manager.broadcast("player_update", {"player_id": player_id})

    # 检查是否是"终结"选项
    is_terminal = "💀" in (opt["player_gain"] or "") or "终结" in (opt["player_gain"] or "")

    return {
        "ok": True,
        "option_key": option_key,
        "option_text": opt["option_text"],
        "result_text": opt["result_text"],
        "player_gain": opt["player_gain"] or "",
        "node_number": cur_node["node_number"],
        "node_title": cur_node["title"],
        "is_terminal": is_terminal,
        "time_result": time_result,
    }


@app.get("/api/stats")
async def get_stats():
    return fetch_stats()


# ── API: 玩家操作 ───────────────────────────────────────────
@app.post("/api/players")
async def create_player(request: Request):
    data = await _json_body(request)
    name = data.get("name", "").strip()
    if not name: return {"ok": False, "error": "玩家名称不能为空"}
    db = get_db()
    try:
        cur = db.execute("INSERT INTO players (name) VALUES (?)", (name,))
        db.commit()
        pid = cur.lastrowid
    except Exception as e:
        db.close(); return {"ok": False, "error": str(e)}
    db.close()
    return {"ok": True, "player_id": pid}


@app.put("/api/player/{player_id}")
async def update_player(player_id: int, request: Request):
    data = await _json_body(request)
    db = get_db()
    fields = {k: data[k] for k in ["name","current_location","gold","inventory",
                                     "aspect_levels","status","notes"] if k in data}
    if not fields:
        db.close(); return {"ok": False, "error": "没有要更新的字段"}

    # 如果设置了位置，自动发现该区域
    if "current_location" in fields:
        import json as _json
        loc = fetch_location_by_name(fields["current_location"])
        if loc:
            player = _d(fetch_player(player_id))
            discovered = _json.loads((player or {}).get("discovered_locations") or "[]")
            if loc["id"] not in discovered:
                discovered.append(loc["id"])
            # 也发现相邻区域
            connected_locs = _ds(fetch_connected_locations(loc["id"]))
            for cl in connected_locs:
                if cl["id"] not in discovered:
                    discovered.append(cl["id"])
            fields["discovered_locations"] = _json.dumps(discovered, ensure_ascii=False)

    sets = ", ".join(f"{k}=?" for k in fields)
    vals = list(fields.values()) + [player_id]
    db.execute(f"UPDATE players SET {sets} WHERE id=?", vals)
    db.commit(); db.close()
    return {"ok": True}


@app.post("/api/player/{player_id}/action")
async def log_player_action(player_id: int, request: Request):
    data = await _json_body(request)
    db = get_db()
    db.execute(
        "INSERT INTO player_action_log (player_id,round_number,action_type,action_text,"
        "result_text,npc_id,location) VALUES (?,?,?,?,?,?,?)",
        (player_id, data.get("round_number"), data.get("action_type"),
         data.get("action_text",""), data.get("result_text",""),
         data.get("npc_id"), data.get("location")))
    db.commit(); db.close()
    return {"ok": True}


@app.get("/api/player/{player_id}/actions")
async def get_player_actions(player_id: int):
    return fetch_player_actions(player_id)

import random

# ── 玩家面板页面 ──────────────────────────────────────────
@app.get("/player/{player_id}/panel", response_class=HTMLResponse)
async def player_panel(request: Request, player_id: int):
    player = _d(fetch_player(player_id))
    if not player:
        return HTMLResponse("Player not found", status_code=404)
    nav = get_nav_data()
    # 获取当前位置信息
    location_info = None
    connected = []
    npcs_here = []
    if player.get("current_location"):
        loc = fetch_location_by_name(player["current_location"])
        if loc:
            location_info = _d(loc)
            connected = _ds(fetch_connected_locations(loc["id"]))
            # 使用智能过滤：有剧情线的NPC只在当前节点所在地出现
            player_time = player.get("game_time", 480) if isinstance(player, dict) else 480
            npcs_here = fetch_npcs_at_location_filtered(
                loc["name"], loc["region_num"] or "", player_time
            )
    # 获取时间信息
    time_info = get_player_time_info(player_id)
    # 获取所有区域（用于手动设置初始位置）
    all_locations = _ds(fetch_all_locations())
    # 获取行动日志
    player_actions = fetch_player_actions(player_id, limit=30)
    return HTMLResponse(render(
        "player_panel.html", request=request, player=player, nav=nav,
        location_info=location_info, connected=connected,
        npcs_here=npcs_here, time_info=time_info,
        all_locations=all_locations, player_actions=player_actions,
        aspect_labels={"灯":"🔆灯","蛾":"🦋蛾","刃":"⚔️刃","铸":"🔨铸","冬":"❄️冬","心":"💓心"},
    ))


# ── 玩家面板 API ──────────────────────────────────────────
@app.post("/api/player/{player_id}/move")
async def move_player(player_id: int, request: Request):
    data = await _json_body(request)
    target_location_id = data.get("target_location_id")
    if not target_location_id:
        return {"ok": False, "error": "请选择目标区域"}

    player = _d(fetch_player(player_id))
    if not player:
        return {"ok": False, "error": "玩家不存在"}

    target = _d(fetch_location(target_location_id))
    if not target:
        return {"ok": False, "error": "目标区域不存在"}

    # 计算旅行时间
    travel_time_h = float(data.get("travel_time", 0.5))
    travel_time_min = int(travel_time_h * 60)

    # 推进时间
    old_loc = player.get("current_location") or "未知"
    time_result = advance_game_time(player_id, travel_time_min)

    # 更新玩家位置 + 自动发现新区域
    db = get_db()
    import json as _json

    # 自动发现目标区域及其连接区域
    discovered = _json.loads(player.get("discovered_locations") or "[]")
    if target["id"] not in discovered:
        discovered.append(target["id"])
    # 同时发现目标区域的所有连接区域
    connected_locs = _ds(fetch_connected_locations(target["id"]))
    for cl in connected_locs:
        if cl["id"] not in discovered:
            discovered.append(cl["id"])
    db.execute("UPDATE players SET current_location = ?, discovered_locations = ? WHERE id = ?",
               (target["name"], _json.dumps(discovered, ensure_ascii=False), player_id))
    # 移动可能消耗少量金币（车马费）
    cost = 0
    if travel_time_h >= 1.0:
        cost = int(travel_time_h * 3)  # 远距离收点车马费
        db.execute("UPDATE players SET gold = MAX(0, gold - ?) WHERE id = ?",
                   (cost, player_id))
    db.commit()
    db.close()

    # 记录行动日志
    log_msg = f"🚶 移动: {target['name']} ← {old_loc} (花费{travel_time_h}h)"
    if cost > 0:
        log_msg += f" 车马费 💰{cost}"
    _log_player_action(player_id, 0, "移动", log_msg, "", None, target["name"])

    await manager.broadcast("player_update", {"player_id": player_id})

    return {"ok": True, "new_location": target["name"],
            "location_id": target["id"],
            "time_cost": travel_time_min,
            "time_result": time_result,
            "gold_cost": cost,
            "log": log_msg}


@app.post("/api/player/{player_id}/explore")
async def explore_location(player_id: int, request: Request):
    player = _d(fetch_player(player_id))
    if not player:
        return {"ok": False, "error": "玩家不存在"}
    if not player.get("current_location"):
        return {"ok": False, "error": "玩家尚未设置位置，请先移动到某个区域"}

    loc = fetch_location_by_name(player["current_location"])
    loc_dict = _d(loc) if loc else None

    # 探索耗时0.5h
    travel_time_min = 30
    time_result = advance_game_time(player_id, travel_time_min)

    # 修正值计算
    aspect_levels = json.loads(player.get("aspect_levels", "{}"))
    max_aspect = max(aspect_levels.values()) if aspect_levels else 0
    explore_bonus = max_aspect // 4  # Lv4+ = +1, Lv8+ = +2, Lv12+ = +3

    # 时间段修正
    game_hour = player.get("game_time", 480) // 60
    if game_hour >= 22 or game_hour < 8:  # 深夜惩罚
        # 蛾/冬/灯免疫
        has_immunity = any(aspect_levels.get(a, 0) >= 2 for a in ["蛾", "冬", "灯"])
        if not has_immunity:
            explore_bonus -= 2

    # 已探索次数修正
    db = get_db()
    explore_count = db.execute(
        "SELECT COUNT(*) FROM player_action_log WHERE player_id=? AND action_type='探索' AND location=?",
        (player_id, player["current_location"])
    ).fetchone()[0]
    db.close()
    if explore_count >= 3:
        explore_bonus -= 1  # 逐渐搜刮干净

    # 掷骰
    roll = random.randint(1, 20)
    effective_roll = min(20, max(1, roll + explore_bonus))

    # 查询搜索池
    gold_found = 0
    items_found = []
    description = ""

    if loc_dict:
        pool_result = _d(fetch_search_pool(loc_dict["region_num"], effective_roll))
    else:
        pool_result = None

    if pool_result:
        if pool_result.get("gold_amount"):
            gold_found = pool_result["gold_amount"]
        if pool_result.get("item_name"):
            item_name = pool_result["item_name"]
            item_category = pool_result.get("item_category", "杂物")
            qty = pool_result.get("quantity", 1)

            # 如果是"随机密传"，从目录中随机选取
            if "随机" in item_name and "密传" in item_name:
                lore = _d(fetch_random_lore())
                if lore:
                    item_name = lore["name"]
                    item_category = lore["category"]
                    add_player_item(player_id, item_id=lore["id"], item_name=item_name, category=item_category, quantity=qty)
                else:
                    item_name = "破损的书页"
                    item_category = "杂物"
                    add_player_item(player_id, item_name=item_name, category=item_category, quantity=qty)
            else:
                existing_item = _d(fetch_item(item_name=item_name))
                item_id_val = existing_item["id"] if existing_item else None
                add_player_item(player_id, item_id=item_id_val, item_name=item_name, category=item_category, quantity=qty)

            items_found.append({"name": item_name, "category": item_category, "quantity": qty})
        description = pool_result.get("description", "")

    # 如果搜索池没有结果（后备：纯金币）
    if not pool_result:
        if effective_roll <= 3:
            gold_found = 0
            description = "你翻遍了周围的角落，除了灰尘和老鼠屎什么也没找到。也许下次运气会好些。"
        elif effective_roll <= 10:
            gold_found = random.randint(5, 15)
            description = "你在角落的暗格里发现了一些被遗忘的钱袋。"
        elif effective_roll <= 17:
            gold_found = random.randint(16, 30)
            description = "你仔细搜索了每一个缝隙，收获颇丰。"
        else:
            gold_found = random.randint(31, 50)
            description = "你的目光被一处隐蔽的凹槽吸引——里面藏着一袋相当可观的金币。运气站在你这边。"

    # 更新金币
    if gold_found > 0:
        add_player_gold(player_id, gold_found)

    # 日志
    item_desc = "、".join([f"{i['name']}×{i['quantity']}" for i in items_found]) if items_found else ""
    gold_desc = f"💰 {gold_found}G" if gold_found > 0 else ""
    full_desc = " + ".join(filter(None, [gold_desc, item_desc])) if (gold_found > 0 or items_found) else "空手而归"
    log_msg = f"🔍 探索 {player['current_location']} (掷骰={effective_roll}) → {full_desc}"
    _log_player_action(player_id, 0, "探索", log_msg, description, None, player["current_location"])

    await manager.broadcast("player_update", {"player_id": player_id})

    return {"ok": True, "roll": roll, "effective_roll": effective_roll,
            "gold_found": gold_found, "items_found": items_found,
            "description": description, "time_result": time_result, "log": log_msg}


@app.get("/api/player/{player_id}/inventory")
async def get_inventory(player_id: int):
    """获取玩家库存"""
    player = _d(fetch_player(player_id))
    if not player:
        return {"ok": False, "error": "玩家不存在"}
    inventory = fetch_player_inventory(player_id)
    items = [_d(row) for row in inventory]
    return {"ok": True, "player_id": player_id, "inventory": items, "gold": player.get("gold", 0)}


@app.post("/api/player/{player_id}/socialize")
async def socialize_with_npc(player_id: int, request: Request):
    data = await _json_body(request)
    npc_id = data.get("npc_id")
    action_type = data.get("action_type", "交谈")

    player = _d(fetch_player(player_id))
    if not player:
        return {"ok": False, "error": "玩家不存在"}

    npc = _d(fetch_npc(npc_id))
    if not npc:
        return {"ok": False, "error": "NPC不存在"}

    # 交互耗时
    time_costs = {"交谈": 30, "交易": 30, "说服": 60, "威胁": 60, "招募": 120}
    cost_min = time_costs.get(action_type, 30)
    time_result = advance_game_time(player_id, cost_min)

    # 生成结果（简化：不同交互类型有不同结果风格）
    action_emoji = {"交谈": "💬", "交易": "🤝", "说服": "🗣️", "威胁": "⚡", "招募": "🤲"}
    emoji = action_emoji.get(action_type, "💬")

    # 根据交互类型生成结果
    if action_type == "交谈":
        results = [
            f"「{npc['name']}」和你聊了一会儿。她/他提到了最近城里的一些奇怪动静——"
            f"但不愿多说。「有些事知道得太多对你没好处。」",
            f"「{npc['name']}」看起来有些警惕，但最终还是分享了一些有用的情报。"
            f"你得知附近有几个值得注意的人物。",
            f"「{npc['name']}」今天心情不错，跟你多聊了几句。你捕捉到了一些关于地下拍卖的传闻。",
        ]
    elif action_type == "交易":
        gold_cost = random.randint(3, 15)
        db = get_db()
        db.execute("UPDATE players SET gold = MAX(0, gold - ?) WHERE id = ?",
                   (gold_cost, player_id))
        db.commit()
        db.close()
        results = [
            f"你花了 💰{gold_cost} 金币从「{npc['name']}」那里换到了一些有用的情报。"
            f"「这东西我收了很久——但你需要它比我更需要。」",
        ]
    elif action_type == "说服":
        results = [
            f"你试图说服「{npc['name']}」——她/他犹豫了很久，最终勉强点头。"
            f"「好吧。但如果你把这事说出去——我没有跟你说过。」",
            f"「{npc['name']}」摇了摇头——「你的理由不够。下次带着更有分量的东西来。」",
        ]
    elif action_type == "威胁":
        results = [
            f"你亮出了底线。「{npc['name']}」的眼神变了——不是恐惧，是评估。"
            f"「你知道你在做什么吗？」",
        ]
    elif action_type == "招募":
        results = [
            f"你向「{npc['name']}」提出了邀请。她/他沉默了一会儿——"
            f"「让我考虑一下。这种事不能现在答复。」",
        ]
    else:
        results = [f"你与「{npc['name']}」进行了互动。"]

    result_text = random.choice(results)

    log_msg = f"{emoji} 与「{npc['name']}」{action_type} (花费{cost_min/60:.1f}h)"
    _log_player_action(player_id, 0, action_type, log_msg, result_text, npc_id, player.get("current_location"))

    await manager.broadcast("player_update", {"player_id": player_id})

    return {"ok": True, "result_text": result_text, "time_result": time_result,
            "log": log_msg, "npc_name": npc["name"]}


@app.get("/api/player/{player_id}/time-info")
async def player_time_info(player_id: int):
    info = get_player_time_info(player_id)
    return info or {"error": "玩家不存在"}


@app.get("/api/location/{location_id}/info")
async def location_info(location_id: int, player_id: int = None):
    loc = _d(fetch_location(location_id))
    if not loc:
        return {"ok": False, "error": "区域不存在"}
    connected = _ds(fetch_connected_locations(location_id))
    # 使用智能过滤
    player_time = 480
    if player_id:
        ti = get_player_time_info(player_id)
        if ti:
            player_time = ti["game_time"]
    npcs_here = fetch_npcs_at_location_filtered(
        loc["name"], loc["region_num"] or "", player_time
    )
    return {"ok": True, "location": loc, "connected": connected, "npcs": npcs_here}


@app.get("/api/player/{player_id}/map")
async def player_map(player_id: int):
    """获取玩家的已解锁地图数据（用于可视化）"""
    player = _d(fetch_player(player_id))
    if not player:
        return {"ok": False, "error": "玩家不存在"}

    import json as _json
    discovered_ids = _json.loads(player.get("discovered_locations") or "[]")

    # 获取所有区域
    all_locations = _ds(fetch_all_locations())

    # 获取当前区域
    current_loc = fetch_location_by_name(player.get("current_location") or "")
    current_id = current_loc["id"] if current_loc else None

    # 构建地图数据
    map_data = []
    for loc in all_locations:
        loc_id = loc["id"]
        is_discovered = loc_id in discovered_ids
        is_current = loc_id == current_id

        # 获取该区域的连接（仅当区域已发现时返回连接）
        connections = []
        if is_discovered:
            conns = _ds(fetch_connected_locations(loc_id))
            for c in conns:
                connections.append({
                    "target_id": c["id"],
                    "target_name": c["name"],
                    "target_region_num": c["region_num"],
                    "travel_time": c["travel_time"],
                    "is_special": c.get("is_special", False),
                    "is_discovered": c["id"] in discovered_ids,
                })

        map_data.append({
            "id": loc_id,
            "region_num": loc["region_num"],
            "name": loc["name"],
            "english": loc["english"],
            "travel_type": loc["travel_type"],
            "is_discovered": is_discovered,
            "is_current": is_current,
            "connections": connections,
        })

    return {
        "ok": True,
        "player_id": player_id,
        "current_location_id": current_id,
        "discovered_count": len(discovered_ids),
        "total_locations": len(all_locations),
        "locations": map_data,
    }


def _log_player_action(player_id, round_num, action_type, action_text, result_text, npc_id, location):
    """内部辅助：记录玩家行动"""
    db = get_db()
    db.execute(
        "INSERT INTO player_action_log (player_id, round_number, action_type, action_text,"
        "result_text, npc_id, location) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (player_id, round_num, action_type, action_text, result_text, npc_id, location))
    db.commit()
    db.close()



@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ── 启动 ───────────────────────────────────────────────────
if __name__ == "__main__":
    import os, socket
    port = int(os.environ.get("PORT", 8000))
    hostname = socket.gethostbyname(socket.gethostname())
    border = "=" * 50
    print(border)
    print("  隐秘爱丁堡 - NPC剧情线管理工具")
    print(border)
    if "PORT" in os.environ:
        print(f"  部署模式 - 端口: {port}")
    else:
        print(f"  本地:  http://127.0.0.1:{port}")
        print(f"  网络:  http://{hostname}:{port}")
    print(border)
    uvicorn.run(app, host="0.0.0.0", port=port)
