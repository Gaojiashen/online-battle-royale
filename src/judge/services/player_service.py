"""
玩家业务服务 — 用例编排层

协调 engine（战斗逻辑）、PostgreSQL（持久化读写）、models（数据结构）
完成玩家客户端所需的全部操作。
"""
import json
import logging
from typing import Optional, List, Tuple

from engine.card_library import ALL_CARDS, CARDS_BY_ID, get_card
from engine.deck_validator import DECK_SIZE

try:
    import asyncpg  # noqa: F401
    _asyncpg_available = True
except ImportError:
    asyncpg = None  # type: ignore
    _asyncpg_available = False

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════
# PostgreSQL 连接池引用
# ════════════════════════════════════════════════════

_pg_pool = None


def set_pg_read_pool(pool):
    """由 app.py lifespan 调用，注入 PG 连接池。"""
    global _pg_pool
    _pg_pool = pool


def _use_pg():
    """检查 PG 连接池是否可用。"""
    return _pg_pool is not None


# ════════════════════════════════════════════════════
# 玩家查找
# ════════════════════════════════════════════════════

async def lookup_player(name: str) -> dict:
    """按名称查找玩家，返回性相等级和当前对战信息"""
    try:
        # 1. 查玩家战斗状态表 → 获取当前对战
        battle = await _find_player_battle(name)
        has_battle = battle is not None
        battle_id = ""
        battle_state = ""
        if has_battle:
            battle_id = battle["fields"].get("对战ID", "")
            battle_state = await _get_battle_state(battle_id)

        # 2. 查玩家表 → 获取性相
        aspects = {}
        game_hp = 0
        if _use_pg():
            player = await _get_player_from_pg(_pg_pool, name)
            if player is not None:
                aspects = _extract_aspects(player["fields"])
                game_hp = player["fields"].get("游戏HP", 0) or 0

        return {
            "ok": True,
            "player_name": name,
            "aspects": aspects,
            "game_hp": game_hp,
            "has_battle": has_battle,
            "battle_id": battle_id,
            "battle_state": battle_state,
        }
    except Exception:
        logger.exception(f"lookup_player failed for name={name}")
        raise


# ════════════════════════════════════════════════════
# 玩家对战历史
# ════════════════════════════════════════════════════

async def get_player_battles(name: str) -> dict:
    """获取玩家所有对战列表（活跃 + 已完成）— PG JOIN 查询"""
    my_records = []
    battle_index = {}

    # Phase 5.1-B: PG 优先（一次 JOIN）
    if _use_pg():
        pg_recs, pg_idx = await _get_player_battles_from_pg(_pg_pool, name)
        if pg_recs:
            my_records = pg_recs
            # battle_index 从 pg_idx 转换格式以匹配旧代码
            for bid, bi in pg_idx.items():
                battle_index[bid] = bi["fields"]
        else:
            # PG 无数据，fall through to Feishu
            pass

    active = []
    finished = []

    for r in my_records:
        fields = r.get("fields", {})
        battle_id = fields.get("对战ID", "")
        side = fields.get("玩家侧", "")
        bf = battle_index.get(battle_id)
        if not bf:
            continue

        opponent = bf.get("玩家B名称", "") if side == "A" else bf.get("玩家A名称", "")
        state = bf.get("状态", "")
        winner_name = bf.get("胜者", "") or ""

        if state != "已结束":
            result = "进行中"
        elif not winner_name or winner_name == "draw":
            result = "平局"
        elif winner_name.upper() == side.upper():
            result = "胜利"
        else:
            result = "失败"

        entry = {
            "battle_id": battle_id,
            "opponent": opponent,
            "my_side": side,
            "state": state,
            "result": result,
            "winner": winner_name,
            "total_rounds": _int_field({"fields": bf}, "当前回合", 0),
            "created_at": bf.get("创建时间", ""),
        }

        if state == "已结束":
            finished.append(entry)
        else:
            active.append(entry)

    finished.sort(key=lambda b: b["created_at"], reverse=True)

    return {
        "ok": True,
        "player_name": name,
        "active": active,
        "finished": finished,
    }


# ════════════════════════════════════════════════════
# Session 恢复辅助
# ════════════════════════════════════════════════════

async def _restore_session_from_base(battle_id: str, battle_manager) -> bool:
    """从 PG/Base 读取数据并调用 restore_full_session 恢复 BattleSession。
    从 PG 恢复 BattleSession。返回 True 表示恢复成功。"""
    try:
        battle_record = None
        state_a = None
        state_b = None
        sub_a = None
        sub_b = None

        # Phase 5.1-B: PG 优先
        if _use_pg():
            battle_record = await _get_battle_from_pg(_pg_pool, battle_id)
            state_a = await _get_player_state_from_pg(_pg_pool, battle_id, "A")
            state_b = await _get_player_state_from_pg(_pg_pool, battle_id, "B")
            pg_subs = await _get_submissions_from_pg(_pg_pool, battle_id)
            for s in pg_subs:
                f = s.get("fields", {})
                sd = f.get("玩家侧", "")
                card = f.get("选择的卡牌ID", "")
                if sd == "A":
                    sub_a = card
                elif sd == "B":
                    sub_b = card
            if battle_record and state_a and state_b:
                battle_manager.restore_full_session(
                    battle_id=battle_id,
                    battle_record=battle_record,
                    state_a_record=state_a,
                    state_b_record=state_b,
                    submission_a_card=sub_a,
                    submission_b_card=sub_b,
                )
                logger.info(f"Session {battle_id} 已从 PG 恢复")
                return True

        logger.warning(f"恢复失败: {battle_id} 数据不完整")
        return False
    except Exception as e:
        logger.error(f"恢复 Session {battle_id} 失败: {e}")
        return False


# ════════════════════════════════════════════════════
# 战斗状态（玩家视角）
# ════════════════════════════════════════════════════

async def get_player_battle(name: str, battle_manager=None, battle_id: str = "") -> dict:
    """获取玩家当前战斗的完整状态（玩家视角）"""
    # 1. 找战斗：优先使用指定的 battle_id
    if battle_id:
        battle = await _find_player_in_battle(name, battle_id)
        if not battle:
            return {"ok": False, "message": f"玩家 {name} 不在对战 {battle_id} 中"}
        side = battle["fields"].get("玩家侧", "")
    else:
        battle = await _find_player_battle(name)
        if not battle:
            return {"ok": False, "message": f"玩家 {name} 没有进行中的战斗"}
        battle_id = battle["fields"].get("对战ID", "")
        side = battle["fields"].get("玩家侧", "")

    # 1.5 如果 Session 丢失（服务重启），尝试恢复
    if battle_manager is not None and battle_id not in battle_manager._battles:
        await _restore_session_from_base(battle_id, battle_manager)

    # ── 内存优先路径 ──
    session = battle_manager._battles.get(battle_id) if battle_manager else None

    if session and session.state_a and session.state_b:
        is_a = (side == "A")
        my_state = session.state_a if is_a else session.state_b
        opp_state = session.state_b if is_a else session.state_a

        my_hp = my_state.hp
        opp_hp = opp_state.hp
        my_resources = {
            "edge": my_state.edge, "phantom": my_state.phantom,
            "charge": my_state.charge, "chill": my_state.self_chill,
            "pulse": my_state.pulse, "read": my_state.read,
            "insight": my_state.insight,
        }
        sub = session.submission_a if is_a else session.submission_b
        my_submitted = sub is not None
        deck_confirmed = True
        deck_locked = session.state != "deck_selection"
        current_round = session.current_round
        state_str = session.state
        opponent = session.player_b_name if is_a else session.player_a_name
        my_deck_ids = session.player_a_deck if is_a else session.player_b_deck
        opp_deck_ids = session.player_b_deck if is_a else session.player_a_deck
        winner = session.winner

        return {
            "ok": True,
            "battle_id": battle_id,
            "state": state_str,
            "current_round": current_round,
            "my_side": side,
            "opponent_name": opponent,
            "my_hp": my_hp,
            "opponent_hp": opp_hp,
            "my_resources": my_resources,
            "my_deck": _deck_to_detail(my_deck_ids, include_effect=True),
            "opponent_deck": _deck_to_detail(opp_deck_ids, include_effect=False),
            "deck_confirmed": deck_confirmed,
            "deck_locked": deck_locked,
            "my_submitted_this_round": my_submitted,
            "winner": winner or None,
        }

    # ── PG / Feishu fallback ──
    # 2. 从对战管理查回合/状态/胜者 + 对手名
    state_info = await _get_battle_record(battle_id)
    if state_info is None:
        return {"ok": False, "message": f"对战 {battle_id} 不存在"}
    opponent = (state_info["fields"].get("玩家B名称", "")
                if side == "A" else state_info["fields"].get("玩家A名称", ""))

    # 4. 从玩家战斗状态查 HP + 资源
    my_record = await _get_player_state_record(battle_id, side)
    opp_record = await _get_player_state_record(battle_id, _other_side(side))

    my_hp = _int_field(my_record, "战HP", 20)
    opp_hp = _int_field(opp_record, "战HP", 20) if opp_record else 20

    # 5. 读牌库
    my_deck_ids = _read_deck_slots(my_record)
    opp_deck_ids = _read_deck_slots(opp_record)
    deck_confirmed = _bool_field(my_record, "牌库已确认")
    deck_locked = (state_info["fields"].get("状态", "") not in ("已初始化", "选牌中"))

    # 6. 检查本回合是否已提交 — 优先读内存
    my_submitted = await _has_submitted_this_round(battle_id, side,
                                                     _int_field(state_info, "当前回合", 0),
                                                     battle_manager)

    return {
        "ok": True,
        "battle_id": battle_id,
        "state": state_info["fields"].get("状态", ""),
        "current_round": _int_field(state_info, "当前回合", 0),
        "my_side": side,
        "opponent_name": opponent,
        "my_hp": my_hp,
        "opponent_hp": opp_hp,
        "my_resources": _extract_resources(my_record),
        "my_deck": _deck_to_detail(my_deck_ids, include_effect=True),
        "opponent_deck": _deck_to_detail(opp_deck_ids, include_effect=False),
        "deck_confirmed": deck_confirmed,
        "deck_locked": deck_locked,
        "my_submitted_this_round": my_submitted,
        "winner": state_info["fields"].get("胜者", "") or None,
    }


# ════════════════════════════════════════════════════
# Battle 聚合接口（内存优先，减少 Base 查询）
# ════════════════════════════════════════════════════

async def get_battle_full(name: str, battle_manager=None, battle_id: str = "") -> dict:
    """一次返回前端 refreshAll 需要的全部数据：battle 状态 + 卡牌 + 日志。
    优先读 BattleSession 内存，session 不存在时从 Base 恢复后读取。"""
    # 1. 确定 battle_id 和 side
    if battle_id:
        battle_rec = await _find_player_in_battle(name, battle_id)
        if not battle_rec:
            return {"ok": False, "message": f"玩家 {name} 不在对战 {battle_id} 中"}
        side = battle_rec["fields"].get("玩家侧", "")
    else:
        battle_rec = await _find_player_battle(name)
        if not battle_rec:
            return {"ok": False, "message": f"玩家 {name} 没有进行中的战斗"}
        battle_id = battle_rec["fields"].get("对战ID", "")
        side = battle_rec["fields"].get("玩家侧", "")

    # 2. 确保 session 存在（内存优先，Base 恢复）
    if battle_manager is not None and battle_id not in battle_manager._battles:
        await _restore_session_from_base(battle_id, battle_manager)

    session = battle_manager._battles.get(battle_id) if battle_manager else None

    # 3. 从 Base 获取对手名和状态（始终读 Base 以确保一致，数据量极小）
    state_info = await _get_battle_record(battle_id)
    if state_info is None:
        return {"ok": False, "message": f"对战 {battle_id} 不存在"}
    opponent = (state_info["fields"].get("玩家B名称", "")
                if side == "A" else state_info["fields"].get("玩家A名称", ""))
    state_str = state_info["fields"].get("状态", "")
    current_round = _int_field(state_info, "当前回合", 0)

    # 4. 从内存读取 HP、资源、提交状态（session 存在时）
    if session and session.state_a and session.state_b:
        is_a = (side == "A")
        my_state = session.state_a if is_a else session.state_b
        opp_state = session.state_b if is_a else session.state_a
        my_hp = my_state.hp
        opp_hp = opp_state.hp
        my_resources = {
            "edge": my_state.edge, "phantom": my_state.phantom,
            "charge": my_state.charge, "chill": my_state.self_chill,
            "pulse": my_state.pulse, "read": my_state.read,
            "insight": my_state.insight,
        }
        sub = session.submission_a if is_a else session.submission_b
        my_submitted = sub is not None
        deck_confirmed = True
        deck_locked = session.state != "deck_selection"
        # 使用 session 的 current_round（实时），Base 的可能有延迟
        current_round = session.current_round
    else:
        # Base 回退
        my_record = await _get_player_state_record(battle_id, side)
        opp_record = await _get_player_state_record(battle_id, _other_side(side))
        my_hp = _int_field(my_record, "战HP", 20)
        opp_hp = _int_field(opp_record, "战HP", 20) if opp_record else 20
        my_resources = _extract_resources(my_record)
        my_submitted = await _has_submitted_this_round(battle_id, side, current_round, battle_manager)
        deck_confirmed = _bool_field(my_record, "牌库已确认")
        deck_locked = state_str not in ("已初始化", "选牌中")

    # 5. 牌库详情（内存或 Base）
    if session:
        my_deck_ids = session.player_a_deck if side == "A" else session.player_b_deck
        opp_deck_ids = session.player_b_deck if side == "A" else session.player_a_deck
    else:
        my_record = await _get_player_state_record(battle_id, side)
        opp_record = await _get_player_state_record(battle_id, _other_side(side))
        my_deck_ids = _read_deck_slots(my_record)
        opp_deck_ids = _read_deck_slots(opp_record)
    my_deck = _deck_to_detail(my_deck_ids, include_effect=True)
    opp_deck = _deck_to_detail(opp_deck_ids, include_effect=False)

    # 6. 可用卡牌（内存 session.available 或实时计算）
    if session:
        avail_ids = session.player_a_available if side == "A" else session.player_b_available
        cards = [_card_summary(cid, cid in my_deck_ids if deck_locked else False) for cid in avail_ids]
    else:
        # Phase 5.1-B: 实时计算替代 TABLE_AVAILABLE 查询
        avail_ids = await _get_available_card_ids(battle_id, side)
        cards = [_card_summary(cid, cid in my_deck_ids if deck_locked else False) for cid in avail_ids]

    # 7. 战斗日志（内存或 Base）
    logs = []
    if session and session.rounds:
        for r in session.rounds:
            mc = r.card_a if side == "A" else r.card_b
            oc = r.card_b if side == "A" else r.card_a
            my_hp_after = r.state_a_after.hp if r.state_a_after else 0
            opp_hp_after = r.state_b_after.hp if r.state_b_after else 0
            if side == "B":
                my_hp_after, opp_hp_after = opp_hp_after, my_hp_after
            logs.append({
                "round": r.round_number,
                "my_card": {"card_id": mc.id, "name": mc.name, "effect_text": mc.effect_text},
                "opponent_card": {"card_id": oc.id, "name": oc.name, "effect_text": oc.effect_text},
                "rps_description": r.rps_description,
                "damage_to_me": r.damage_to_a if side == "A" else r.damage_to_b,
                "damage_to_opponent": r.damage_to_b if side == "A" else r.damage_to_a,
                "my_hp_after": my_hp_after, "opponent_hp_after": opp_hp_after,
                "special_events": r.special_events,
                "my_resource_logs": r.resource_logs_a if side == "A" else r.resource_logs_b,
                "opponent_resource_logs": r.resource_logs_b if side == "A" else r.resource_logs_a,
            })
    else:
        # PG
        log_records = []
        if _use_pg():
            log_records = await _get_battle_rounds_from_pg(_pg_pool, battle_id)
        for lr in log_records:
            f = lr.get("fields", {})
            if f.get("对战ID") == battle_id:
                my_card_str = f.get("A使用卡牌" if side == "A" else "B使用卡牌", "")
                opp_card_str = f.get("B使用卡牌" if side == "A" else "A使用卡牌", "")
                my_cid = my_card_str.split(" ")[0] if my_card_str else ""
                opp_cid = opp_card_str.split(" ")[0] if opp_card_str else ""
                my_card = CARDS_BY_ID.get(my_cid)
                opp_card = CARDS_BY_ID.get(opp_cid)
                logs.append({
                    "round": _int_field(lr, "回合编号", 0),
                    "my_card": {"card_id": my_cid, "name": my_card.name if my_card else my_card_str, "effect_text": my_card.effect_text if my_card else ""},
                    "opponent_card": {"card_id": opp_cid, "name": opp_card.name if opp_card else opp_card_str, "effect_text": opp_card.effect_text if opp_card else ""},
                    "rps_description": f.get("RPS结果描述", ""),
                    "damage_to_me": _int_field(lr, "A受到伤害" if side == "A" else "B受到伤害", 0),
                    "damage_to_opponent": _int_field(lr, "B受到伤害" if side == "A" else "A受到伤害", 0),
                    "my_hp_after": _int_field(lr, "A剩余HP" if side == "A" else "B剩余HP", 20),
                    "opponent_hp_after": _int_field(lr, "B剩余HP" if side == "A" else "A剩余HP", 20),
                    "special_events": (f.get("特殊事件", "") or "").split("; "),
                    "my_resource_logs": [], "opponent_resource_logs": [],
                })
    logs.sort(key=lambda x: x["round"])

    return {
        "ok": True,
        "battle_id": battle_id,
        "state": state_str,
        "current_round": current_round,
        "my_side": side,
        "opponent_name": opponent,
        "my_hp": my_hp,
        "opponent_hp": opp_hp,
        "my_resources": my_resources,
        "my_deck": my_deck,
        "opponent_deck": opp_deck,
        "deck_confirmed": deck_confirmed,
        "deck_locked": deck_locked,
        "my_submitted_this_round": my_submitted,
        "winner": state_info["fields"].get("胜者", "") or None,
        "cards": cards,
        "logs": logs,
    }


def _card_summary(card_id: str, selected: bool = False) -> dict:
    """从 CARDS_BY_ID 生成卡牌摘要"""
    card = CARDS_BY_ID.get(card_id)
    if card:
        return {
            "card_id": card.id, "name": card.name,
            "category": card.category, "aspect": card.aspect,
            "level_requirement": card.level_requirement,
            "effect_text": card.effect_text, "selected": selected,
        }
    return {"card_id": card_id, "name": "", "category": "", "aspect": "",
            "level_requirement": 0, "effect_text": "", "selected": selected}


# ════════════════════════════════════════════════════
# 可用卡牌
# ════════════════════════════════════════════════════

async def get_available_cards(name: str, battle_id: str = "") -> dict:
    """获取当前玩家的可用卡牌列表"""
    if battle_id:
        battle = await _find_player_in_battle(name, battle_id)
        if not battle:
            return {"ok": False, "message": f"玩家 {name} 不在对战 {battle_id} 中"}
        side = battle["fields"].get("玩家侧", "")
    else:
        battle = await _find_player_battle(name)
        if not battle:
            return {"ok": False, "message": f"玩家 {name} 没有进行中的战斗"}
        battle_id = battle["fields"].get("对战ID", "")
        side = battle["fields"].get("玩家侧", "")

    # 检查牌库是否已锁定
    my_record = await _get_player_state_record(battle_id, side)
    deck_locked = _bool_field(my_record, "牌库已确认")
    selected_ids = _read_deck_slots(my_record)

    # Phase 5.1-B: 实时计算替代 TABLE_AVAILABLE 查询
    avail_ids = await _get_available_card_ids(battle_id, side)
    cards = []
    for cid in avail_ids:
        card = CARDS_BY_ID.get(cid)
        cards.append({
            "card_id": cid,
            "name": card.name if card else cid,
            "category": card.category if card else "",
            "aspect": card.aspect if card else "",
            "level_requirement": card.level_requirement if card else 0,
            "effect_text": card.effect_text if card else "",
            "selected": cid in selected_ids if deck_locked else False,
        })

    return {
        "ok": True,
        "battle_id": battle_id,
        "cards": cards,
        "selected_count": len(selected_ids) if deck_locked else 0,
        "deck_size": DECK_SIZE,
        "deck_locked": deck_locked,
    }


# ════════════════════════════════════════════════════
# 牌库确认
# ════════════════════════════════════════════════════

async def select_deck(player_name: str, battle_id: str,
                      card_ids: List[str], battle_manager) -> dict:
    """玩家确认 8 张牌选择 → 写 Base → 检查对手 → 可能触发 confirm_deck"""
    # 1. 确定玩家侧
    battle = await _get_battle_record(battle_id)
    if battle is None:
        return {"ok": False, "message": f"对战不存在: {battle_id}"}
    side = _which_side(battle["fields"], player_name)
    if not side:
        return {"ok": False, "message": f"玩家 {player_name} 不在对战 {battle_id} 中"}

    # 2. 校验卡牌：全部必须在玩家可用牌中
    valid_ids = await _get_available_card_ids(battle_id, side)
    for cid in card_ids:
        if cid not in valid_ids:
            return {"ok": False, "message": f"卡牌 {cid} 不在可用列表中"}

    # 3. 写入 PG（牌位1-8 + 牌库已确认）
    if not _use_pg():
        return {"ok": False, "message": "数据库不可用，请稍后重试"}
    try:
        await _pg_pool.execute(
            "UPDATE battle_players SET deck_slots = $1::jsonb, "
            "deck_confirmed = TRUE, updated_at = NOW() "
            "WHERE battle_id = $2 AND side = $3",
            json.dumps(card_ids), battle_id, side,
        )
    except Exception:
        logger.error(f"PG sync_deck_confirmed failed for {battle_id}/{side}", exc_info=True)
        return {"ok": False, "message": "牌库写入失败，请稍后重试"}

    # 4. 检查双方是否均已确认
    both_ready = False
    try:
        rows = await _pg_pool.fetch(
            "SELECT deck_confirmed FROM battle_players WHERE battle_id = $1",
            battle_id,
        )
        both_ready = len(rows) >= 2 and all(r["deck_confirmed"] for r in rows)
    except Exception:
        logger.warning(
            f"PG deck_confirmed check failed for {battle_id}", exc_info=True
        )

    if both_ready:
        # 5. 从 Base 读取双方牌库
        my_record = await _get_player_state_record(battle_id, side)
        opp_record = await _get_player_state_record(battle_id, _other_side(side))
        a_deck = _read_deck_slots(my_record) if side == "A" else _read_deck_slots(opp_record)
        b_deck = _read_deck_slots(opp_record) if side == "A" else _read_deck_slots(my_record)

        if len(a_deck) == 0 or len(b_deck) == 0 or len(a_deck) > DECK_SIZE or len(b_deck) > DECK_SIZE:
            return {"ok": False, "status": "error",
                    "message": f"牌库数量无效 A:{len(a_deck)} B:{len(b_deck)}（需要 1-{DECK_SIZE} 张）"}

        # 5.5 如果 Session 因服务重启丢失，从 Base 重建
        if battle_id not in battle_manager._battles:
            import json
            a_name = battle["fields"].get("玩家A名称", "")
            b_name = battle["fields"].get("玩家B名称", "")
            a_aspects_raw = battle["fields"].get("玩家A性相等级", "{}")
            b_aspects_raw = battle["fields"].get("玩家B性相等级", "{}")
            try:
                a_aspects = json.loads(a_aspects_raw) if isinstance(a_aspects_raw, str) else a_aspects_raw
                b_aspects = json.loads(b_aspects_raw) if isinstance(b_aspects_raw, str) else b_aspects_raw
                # 确保值为 int
                a_aspects = {k: int(v) for k, v in a_aspects.items()}
                b_aspects = {k: int(v) for k, v in b_aspects.items()}
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.error(f"解析性相JSON失败: A={a_aspects_raw}, B={b_aspects_raw}")
                return {"ok": False, "status": "error", "message": "无法解析玩家性相数据"}
            battle_manager.restore_session(
                battle_id, a_name, b_name, a_aspects, b_aspects,
            )

        # 6. 调用 BattleManager
        from models import DeckConfirmRequest
        req = DeckConfirmRequest(
            battle_id=battle_id, player_a_deck=a_deck, player_b_deck=b_deck,
        )
        try:
            result = await battle_manager.confirm_deck(req)
            return {
                "ok": True, "status": "battle_started",
                "current_round": result.current_round, "message": result.message,
            }
        except Exception as e:
            return {"ok": False, "status": "error", "message": str(e)}
    else:
        return {
            "ok": True, "status": "waiting_for_opponent",
            "message": "已记录你的牌库，等待对手确认",
        }


# ════════════════════════════════════════════════════
# 出牌提交
# ════════════════════════════════════════════════════

def submit_card(battle_id: str, side: str, card_id: str,
                battle_manager) -> dict:
    """提交本回合出牌 → 直接调 BattleManager"""
    result = battle_manager.submit_card(battle_id, side, card_id)
    resp = {}
    if result.status == "resolved" and result.result:
        r = result.result
        resp = {
            "ok": True, "status": "resolved", "round": result.round,
            "result": {
                "my_card": r.card_a_name if side == "a" else r.card_b_name,
                "opponent_card": r.card_b_name if side == "a" else r.card_a_name,
                "rps_description": r.rps_description,
                "damage_to_me": r.damage_to_a if side == "a" else r.damage_to_b,
                "damage_to_opponent": r.damage_to_b if side == "a" else r.damage_to_a,
                "my_hp_after": r.hp_a_after if side == "a" else r.hp_b_after,
                "opponent_hp_after": r.hp_b_after if side == "a" else r.hp_a_after,
                "special_events": r.special_events,
            },
            "message": "",
        }
    else:
        resp = {
            "ok": True, "status": result.status,
            "round": result.round, "message": result.message,
        }
    return resp


# ════════════════════════════════════════════════════
# 战斗日志（玩家视角）
# ════════════════════════════════════════════════════

async def get_battle_logs(name: str, battle_manager=None, battle_id: str = "") -> dict:
    """获取玩家视角的战斗日志 — 内存优先，Base 回退"""
    if battle_id:
        battle = await _find_player_in_battle(name, battle_id)
        if not battle:
            return {"ok": False, "message": f"玩家 {name} 不在对战 {battle_id} 中"}
        side = battle["fields"].get("玩家侧", "")
    else:
        battle = await _find_player_battle(name)
        if not battle:
            return {"ok": False, "message": f"玩家 {name} 没有进行中的战斗"}
        battle_id = battle["fields"].get("对战ID", "")
        side = battle["fields"].get("玩家侧", "")

    # 如果 Session 丢失，尝试从 Base 恢复（使内存路径可用）
    if battle_manager is not None and battle_id not in battle_manager._battles:
        await _restore_session_from_base(battle_id, battle_manager)

    # 优先读内存（RoundResult 含完整 Card 对象、资源日志、特殊事件）
    if battle_manager is not None:
        session = battle_manager._battles.get(battle_id)
        if session is not None and session.rounds:
            logs = []
            for r in session.rounds:
                my_card = r.card_a if side == "A" else r.card_b
                opp_card = r.card_b if side == "A" else r.card_a
                my_resources = r.resource_logs_a if side == "A" else r.resource_logs_b
                opp_resources = r.resource_logs_b if side == "A" else r.resource_logs_a
                my_hp_after = r.state_a_after.hp if r.state_a_after else 0 if side == "A" else r.state_b_after.hp if r.state_b_after else 0
                opp_hp_after = r.state_b_after.hp if r.state_b_after else 0 if side == "A" else r.state_a_after.hp if r.state_a_after else 0
                logs.append({
                    "round": r.round_number,
                    "my_card": {
                        "card_id": my_card.id, "name": my_card.name,
                        "category": my_card.category, "aspect": my_card.aspect,
                        "level_requirement": my_card.level_requirement,
                        "effect_text": my_card.effect_text,
                    },
                    "opponent_card": {
                        "card_id": opp_card.id, "name": opp_card.name,
                        "category": opp_card.category, "aspect": opp_card.aspect,
                        "level_requirement": opp_card.level_requirement,
                        "effect_text": opp_card.effect_text,
                    },
                    "rps_description": r.rps_description,
                    "damage_to_me": r.damage_to_a if side == "A" else r.damage_to_b,
                    "damage_to_opponent": r.damage_to_b if side == "A" else r.damage_to_a,
                    "my_hp_after": my_hp_after,
                    "opponent_hp_after": opp_hp_after,
                    "special_events": r.special_events,
                    "my_resource_logs": my_resources,
                    "opponent_resource_logs": opp_resources,
                })
            logs.sort(key=lambda x: x["round"])
            return {"ok": True, "battle_id": battle_id, "logs": logs}

    # PG
    records = []
    if _use_pg():
        records = await _get_battle_rounds_from_pg(_pg_pool, battle_id)
    logs = []
    for r in records:
        fields = r.get("fields", {})
        if fields.get("对战ID") == battle_id:
            my_card_str = fields.get("A使用卡牌" if side == "A" else "B使用卡牌", "")
            opp_card_str = fields.get("B使用卡牌" if side == "A" else "A使用卡牌", "")
            my_card_id = my_card_str.split(" ")[0] if my_card_str else ""
            opp_card_id = opp_card_str.split(" ")[0] if opp_card_str else ""
            my_card = CARDS_BY_ID.get(my_card_id)
            opp_card = CARDS_BY_ID.get(opp_card_id)
            logs.append({
                "round": _int_field(r, "回合编号", 0),
                "my_card": {
                    "card_id": my_card_id, "name": my_card.name if my_card else my_card_str,
                    "category": my_card.category if my_card else "",
                    "aspect": my_card.aspect if my_card else "",
                    "level_requirement": my_card.level_requirement if my_card else 0,
                    "effect_text": my_card.effect_text if my_card else "",
                },
                "opponent_card": {
                    "card_id": opp_card_id, "name": opp_card.name if opp_card else opp_card_str,
                    "category": opp_card.category if opp_card else "",
                    "aspect": opp_card.aspect if opp_card else "",
                    "level_requirement": opp_card.level_requirement if opp_card else 0,
                    "effect_text": opp_card.effect_text if opp_card else "",
                },
                "rps_description": fields.get("RPS结果描述", ""),
                "damage_to_me": _int_field(r, "A受到伤害" if side == "A" else "B受到伤害", 0),
                "damage_to_opponent": _int_field(r, "B受到伤害" if side == "A" else "A受到伤害", 0),
                "my_hp_after": _int_field(r, "A剩余HP" if side == "A" else "B剩余HP", 20),
                "opponent_hp_after": _int_field(r, "B剩余HP" if side == "A" else "A剩余HP", 20),
                "special_events": (fields.get("特殊事件", "") or "").split("; "),
                "my_resource_logs": [],
                "opponent_resource_logs": [],
            })
    logs.sort(key=lambda x: x["round"])
    return {"ok": True, "battle_id": battle_id, "logs": logs}


# ════════════════════════════════════════════════════
# 工具函数（routes 可调用）
# ════════════════════════════════════════════════════

async def get_player_side(name: str) -> Optional[str]:
    """获取玩家在当前对战中的侧 (A/B)，无对战时返回 None"""
    battle = await _find_player_battle(name)
    if not battle:
        return None
    return battle["fields"].get("玩家侧", "") or None


# ════════════════════════════════════════════════════
# 内部辅助
# ════════════════════════════════════════════════════

def _other_side(side: str) -> str:
    return "B" if side == "A" else "A"


def _which_side(fields: dict, name: str) -> str:
    if fields.get("玩家A名称", "") == name:
        return "A"
    if fields.get("玩家B名称", "") == name:
        return "B"
    # 兜底：查玩家战斗状态表
    return ""


def _int_field(record, field_name: str, default: int = 0) -> int:
    if record is None:
        return default
    val = record.get("fields", {}).get(field_name, default)
    return val if val is not None else default


def _bool_field(record, field_name: str) -> bool:
    if record is None:
        return False
    return record.get("fields", {}).get(field_name, False) or False


def _extract_aspects(fields: dict) -> dict:
    result = {}
    for asp in ("灯", "蛾", "铸", "冬", "心", "刃"):
        result[asp] = fields.get(asp, 0) or 0
    return result


def _extract_resources(record) -> dict:
    if record is None:
        return {}
    f = record.get("fields", {})
    return {
        "edge": _int_field(record, "锋芒"),
        "phantom": _int_field(record, "幻影"),
        "charge": _int_field(record, "蓄力"),
        "chill": _int_field(record, "寒意"),
        "pulse": _int_field(record, "脉动"),
        "insight": _int_field(record, "看破"),
        "read": _int_field(record, "洞悉"),
    }


def _read_deck_slots(record) -> List[str]:
    """从玩家战斗状态记录中读取牌位1-8"""
    if record is None:
        return []
    f = record.get("fields", {})
    return [f.get(f"牌位{i}", "") or "" for i in range(1, 9) if f.get(f"牌位{i}")]


def _deck_to_detail(deck_ids: List[str], include_effect: bool = True) -> List[dict]:
    """将卡牌ID列表展开为详情列表，include_effect=False 时不返回效果文本"""
    result = []
    for cid in deck_ids:
        card = CARDS_BY_ID.get(cid)
        info = {
            "card_id": cid,
            "name": card.name if card else "",
            "category": card.category if card else "",
            "aspect": card.aspect if card else "",
            "level_requirement": card.level_requirement if card else 0,
        }
        if include_effect:
            info["effect_text"] = card.effect_text if card else ""
        result.append(info)
    return result


async def _get_battle_state(battle_id: str) -> str:
    """查询对战状态。"""
    record = await _get_battle_record(battle_id)
    if record is None:
        return ""
    return record.get("fields", {}).get("状态", "")


async def _get_battle_record(battle_id: str) -> Optional[dict]:
    """从 battles 表查一条记录。"""
    if _use_pg():
        return await _get_battle_from_pg(_pg_pool, battle_id)
    return None


async def _get_player_state_record(battle_id: str, side: str) -> Optional[dict]:
    """从 battle_players 表查指定对战+侧的一条记录。"""
    if _use_pg():
        return await _get_player_state_from_pg(_pg_pool, battle_id, side)
    return None


async def _find_player_in_battle(name: str, battle_id: str) -> Optional[dict]:
    """查找玩家在指定对战中的记录。"""
    if _use_pg():
        for side in ("A", "B"):
            result = await _get_player_state_from_pg(_pg_pool, battle_id, side)
            if result is not None and result.get("fields", {}).get("玩家名称") == name:
                return result
    return None


async def _find_player_battle(name: str) -> Optional[dict]:
    """查找玩家当前活跃对战 — PG only。"""
    if _use_pg():
        recs, idx = await _get_player_battles_from_pg(_pg_pool, name)
        for r in recs:
            bid = r["fields"].get("对战ID", "")
            bi = idx.get(bid, {})
            state = bi.get("fields", {}).get("状态", "")
            if state not in ("已结束", ""):
                return r
        if recs:
            return recs[0]
    return None


async def _get_available_card_ids(battle_id: str, side: str) -> List[str]:
    """获取可用卡牌ID — 实时计算（替代 TABLE_AVAILABLE 查询）"""
    # 从 battles 表读取性相 JSONB，通过 calculate_available 实时计算
    from engine.deck_validator import calculate_available
    record = await _get_battle_record(battle_id)
    if record is None:
        return []
    fields = record.get("fields", {})
    aspects_key = (
        "玩家A性相等级" if side in ("A", "a") else "玩家B性相等级"
    )
    aspects_raw = fields.get(aspects_key, "{}")
    if isinstance(aspects_raw, str):
        try:
            aspects = json.loads(aspects_raw)
        except (json.JSONDecodeError, TypeError):
            return []
    elif isinstance(aspects_raw, dict):
        aspects = aspects_raw
    else:
        return []
    # ensure int values
    aspects = {str(k): int(v) for k, v in aspects.items()}
    cards = calculate_available(aspects)
    return [c.id for c in cards]


async def _has_submitted_this_round(battle_id: str, side: str,
                                    current_round: int, battle_manager=None) -> bool:
    """检查指定侧在当前回合是否已提交 — 内存 > PG > Feishu"""
    if current_round == 0:
        return False

    # 优先 BattleManager 内存
    if battle_manager is not None:
        session = battle_manager._battles.get(battle_id)
        if session is not None:
            sub = session.submission_a if side.upper() == "A" else session.submission_b
            return sub is not None

    # PG fallback
    if _use_pg():
        subs = await _get_submissions_from_pg(_pg_pool, battle_id, side.upper())
        for s in subs:
            if _int_field(s, "回合编号", 0) == current_round:
                return True
    return False


# ════════════════════════════════════════════════════════════════
# Phase 5.1-B — PostgreSQL 查询辅助函数
# 返回格式与现有 Feishu list_records 兼容。
# 所有函数接受 pool 参数，pool=None 时返回 None/空列表。
# 不改变现有业务函数调用路径。
# ════════════════════════════════════════════════════════════════

async def _get_player_from_pg(pool, name: str) -> Optional[dict]:
    """查询玩家帐号 — 查询 players 表。
    异常时返回 None（自动 fallback Feishu）。
    """
    if pool is None:
        return None
    try:
        row = await pool.fetchrow(
            "SELECT name, lantern, moth, forge, winter, heart, blade, game_hp "
            "FROM players WHERE name = $1",
            name,
        )
        if row is None:
            return None
        return {
            "fields": {
                "玩家名称": row["name"],
                "灯": row["lantern"], "蛾": row["moth"],
                "铸": row["forge"], "冬": row["winter"],
                "心": row["heart"], "刃": row["blade"],
                "游戏HP": row["game_hp"],
            },
        }
    except Exception:
        logger.warning(f"PG _get_player_from_pg failed for {name}", exc_info=True)
        return None


async def _get_battle_from_pg(pool, battle_id: str) -> Optional[dict]:
    """查询对战元数据 — 异常时返回 None（自动 fallback Feishu）。"""
    if pool is None:
        return None
    try:
        row = await pool.fetchrow(
            "SELECT battle_id, state, player_a_name, player_b_name, "
            "player_a_aspects, player_b_aspects, current_round, winner, "
            "end_reason, created_at "
            "FROM battles WHERE battle_id = $1",
            battle_id,
        )
        if row is None:
            return None
        return {
            "fields": {
                "对战ID": row["battle_id"],
                "状态": row["state"],
                "玩家A名称": row["player_a_name"],
                "玩家B名称": row["player_b_name"],
                "玩家A性相等级": (
                    json.dumps(row["player_a_aspects"], ensure_ascii=False)
                    if isinstance(row["player_a_aspects"], dict)
                    else row["player_a_aspects"]
                ),
                "玩家B性相等级": (
                    json.dumps(row["player_b_aspects"], ensure_ascii=False)
                    if isinstance(row["player_b_aspects"], dict)
                    else row["player_b_aspects"]
                ),
                "当前回合": row["current_round"],
                "胜者": row["winner"] or "",
                "创建时间": row["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                if row["created_at"] else "",
            },
        }
    except Exception:
        logger.warning(f"PG _get_battle_from_pg failed for {battle_id}", exc_info=True)
        return None


async def _get_player_state_from_pg(pool, battle_id: str, side: str) -> Optional[dict]:
    """查询玩家战斗状态 — 异常时返回 None（自动 fallback Feishu）。"""
    if pool is None:
        return None
    try:
        row = await pool.fetchrow(
            "SELECT battle_id, side, player_name, hp, edge, phantom, charge, "
            "chill, pulse, read, insight, deck_slots, deck_confirmed, submitted "
            "FROM battle_players WHERE battle_id = $1 AND side = $2",
            battle_id, side,
        )
        if row is None:
            return None
        fields = {
            "对战ID": row["battle_id"], "玩家侧": row["side"],
            "玩家名称": row["player_name"], "战HP": row["hp"],
            "锋芒": row["edge"], "幻影": row["phantom"],
            "蓄力": row["charge"], "寒意": row["chill"],
            "脉动": row["pulse"], "洞悉": row["read"],
            "看破": row["insight"],
            "牌库已确认": row["deck_confirmed"],
            "已提交": row["submitted"],
        }
        deck = row["deck_slots"] if isinstance(row["deck_slots"], list) else []
        for i in range(1, 9):
            fields[f"牌位{i}"] = deck[i - 1] if i <= len(deck) else ""
        return {"fields": fields}
    except Exception:
        logger.warning(
            f"PG _get_player_state_from_pg failed for {battle_id}/{side}",
            exc_info=True,
        )
        return None


async def _get_battle_rounds_from_pg(pool, battle_id: str) -> List[dict]:
    """查询回合记录 — 异常时返回空列表（自动 fallback Feishu）。"""
    if pool is None:
        return []
    try:
        rows = await pool.fetch(
            "SELECT battle_id, round_number, card_a_id, card_a_name, "
            "card_b_id, card_b_name, rps_description, damage_to_a, damage_to_b, "
            "hp_a_after, hp_b_after, special_events, winner_side "
            "FROM battle_rounds WHERE battle_id = $1 ORDER BY round_number",
            battle_id,
        )
        result = []
        for row in rows:
            se = row["special_events"]
            special_str = "; ".join(se) if se else ""
            result.append({
                "fields": {
                    "对战ID": row["battle_id"],
                    "回合编号": row["round_number"],
                    "A使用卡牌": (
                        f"{row['card_a_id']} {row['card_a_name']}"
                        if row["card_a_id"] and row["card_a_name"] else ""
                    ),
                    "B使用卡牌": (
                        f"{row['card_b_id']} {row['card_b_name']}"
                        if row["card_b_id"] and row["card_b_name"] else ""
                    ),
                    "RPS结果描述": row["rps_description"] or "",
                    "A受到伤害": row["damage_to_a"],
                    "B受到伤害": row["damage_to_b"],
                    "A剩余HP": row["hp_a_after"] or 0,
                    "B剩余HP": row["hp_b_after"] or 0,
                    "特殊事件": special_str,
                    "胜者": row["winner_side"] or "",
                },
            })
        return result
    except Exception:
        logger.warning(
            f"PG _get_battle_rounds_from_pg failed for {battle_id}", exc_info=True
        )
        return []


async def _get_submissions_from_pg(
    pool, battle_id: str, side: Optional[str] = None
) -> List[dict]:
    """查询提交记录 — 异常时返回空列表（自动 fallback Feishu）。"""
    if pool is None:
        return []
    try:
        if side:
            rows = await pool.fetch(
                "SELECT battle_id, side, player_name, card_id, round_number "
                "FROM battle_submissions "
                "WHERE battle_id = $1 AND side = $2 "
                "ORDER BY created_at",
                battle_id, side,
            )
        else:
            rows = await pool.fetch(
                "SELECT battle_id, side, player_name, card_id, round_number "
                "FROM battle_submissions "
                "WHERE battle_id = $1 "
                "ORDER BY created_at",
                battle_id,
            )
        return [
            {
                "fields": {
                    "对战ID": row["battle_id"], "玩家侧": row["side"],
                    "玩家名称": row["player_name"],
                    "选择的卡牌ID": row["card_id"],
                    "回合编号": row["round_number"],
                },
            }
            for row in rows
        ]
    except Exception:
        logger.warning(
            f"PG _get_submissions_from_pg failed for {battle_id}", exc_info=True
        )
        return []


async def _get_player_battles_from_pg(
    pool, player_name: str
) -> Tuple[List[dict], dict]:
    """查询玩家所有对战 — 一次 JOIN 替代两次全表扫描。
    异常时返回空（自动 fallback Feishu）。
    """
    if pool is None:
        return [], {}
    try:
        rows = await pool.fetch(
            "SELECT bp.battle_id, bp.side, bp.player_name, "
            "b.state, b.player_a_name, b.player_b_name, "
            "b.winner, b.current_round, b.created_at "
            "FROM battle_players bp "
            "JOIN battles b ON bp.battle_id = b.battle_id "
            "WHERE bp.player_name = $1 "
            "ORDER BY b.created_at DESC",
            player_name,
        )
        player_records = []
        battle_index = {}
        for row in rows:
            player_records.append({
                "fields": {
                    "对战ID": row["battle_id"],
                    "玩家侧": row["side"],
                    "玩家名称": row["player_name"],
                },
            })
            if row["battle_id"] not in battle_index:
                battle_index[row["battle_id"]] = {
                    "fields": {
                        "对战ID": row["battle_id"],
                        "状态": row["state"],
                        "玩家A名称": row["player_a_name"],
                        "玩家B名称": row["player_b_name"],
                        "胜者": row["winner"] or "",
                        "当前回合": row["current_round"],
                        "创建时间": row["created_at"].strftime("%Y-%m-%d %H:%M:%S")
                        if row["created_at"] else "",
                    },
                }
        return player_records, battle_index
    except Exception:
        logger.warning(
            f"PG _get_player_battles_from_pg failed for {player_name}", exc_info=True
        )
        return [], {}
