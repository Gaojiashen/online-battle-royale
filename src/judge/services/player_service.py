"""
玩家业务服务 — 用例编排层

协调 engine（战斗逻辑）、integration（Base 读写）、models（数据结构）
完成玩家客户端所需的全部操作。
"""
import os
import logging
from typing import Optional, List, Tuple

from integration.feishu_client import feishu_client
from integration.base_sync import base_sync
from engine.card_library import ALL_CARDS, CARDS_BY_ID, get_card
from engine.deck_validator import DECK_SIZE

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════
# 配置 (从环境变量读取，提供默认值)
# ════════════════════════════════════════════════════

BASE_TOKEN = os.environ.get("FEISHU_BASE_TOKEN", "CB6XbtkLaafJnYsDL8RcHFpEnDg")

# 表ID — 与 base_sync.py 保持一致
TABLE_PLAYERS = os.environ.get("TABLE_PLAYERS", "tbl4KaRcfiz1pZq1")
TABLE_BATTLE = os.environ.get("TABLE_BATTLE", "tblWciOhRlFFEaSr")
TABLE_PLAYER_STATE = os.environ.get("TABLE_PLAYER_STATE", "tblTNAkesS7WlJoR")
TABLE_AVAILABLE = os.environ.get("TABLE_AVAILABLE", "tbl0DDzK6ckrqQah")
TABLE_BATTLE_LOG = os.environ.get("TABLE_BATTLE_LOG", "tblyUL90LNC1Snb5")
TABLE_SUBMISSION = os.environ.get("TABLE_SUBMISSION", "tblcmGlzO76H3RQt")


# ════════════════════════════════════════════════════
# 玩家查找
# ════════════════════════════════════════════════════

async def lookup_player(name: str) -> dict:
    """按名称查找玩家，返回性相等级和当前对战信息"""
    # 1. 查玩家战斗状态表 → 获取当前对战
    battle = await _find_player_battle(name)
    has_battle = battle is not None
    battle_id = ""
    battle_state = ""
    if has_battle:
        battle_id = battle["fields"].get("对战ID", "")
        battle_state = await _get_battle_state(battle_id)

    # 2. 查玩家表 → 获取性相（先试 tbl4KaRcfiz1pZq1 再试 tbl1NnOpplq3x7Rg）
    aspects = {}
    game_hp = 0
    for table_id in (TABLE_PLAYERS, "tbl1NnOpplq3x7Rg"):
        try:
            records = await feishu_client.list_records(BASE_TOKEN, table_id)
        except Exception:
            continue
        for r in records:
            fields = r.get("fields", {})
            found_name = fields.get("玩家名称", "") or fields.get("名称", "")
            if found_name == name:
                aspects = _extract_aspects(fields)
                game_hp = fields.get("游戏HP", 0) or 0
                break
        if aspects:
            break

    return {
        "ok": True,
        "player_name": name,
        "aspects": aspects,
        "game_hp": game_hp,
        "has_battle": has_battle,
        "battle_id": battle_id,
        "battle_state": battle_state,
    }


# ════════════════════════════════════════════════════
# 战斗状态（玩家视角）
# ════════════════════════════════════════════════════

async def get_player_battle(name: str, battle_manager=None) -> dict:
    """获取玩家当前战斗的完整状态（玩家视角）"""
    # 1. 找战斗
    battle = await _find_player_battle(name)
    if not battle:
        return {"ok": False, "message": f"玩家 {name} 没有进行中的战斗"}

    battle_id = battle["fields"].get("对战ID", "")
    side = battle["fields"].get("玩家侧", "")

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
    deck = _read_deck_slots(my_record)
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
        "my_deck": deck,
        "deck_confirmed": deck_confirmed,
        "deck_locked": deck_locked,
        "my_submitted_this_round": my_submitted,
        "winner": state_info["fields"].get("胜者", "") or None,
    }


# ════════════════════════════════════════════════════
# 可用卡牌
# ════════════════════════════════════════════════════

async def get_available_cards(name: str) -> dict:
    """获取当前玩家的可用卡牌列表"""
    battle = await _find_player_battle(name)
    if not battle:
        return {"ok": False, "message": f"玩家 {name} 没有进行中的战斗"}

    battle_id = battle["fields"].get("对战ID", "")
    side = battle["fields"].get("玩家侧", "")

    # 检查牌库是否已锁定
    my_record = await _get_player_state_record(battle_id, side)
    deck_locked = _bool_field(my_record, "牌库已确认")
    selected_ids = _read_deck_slots(my_record)

    records = await feishu_client.list_records(BASE_TOKEN, TABLE_AVAILABLE)
    cards = []
    for r in records:
        fields = r.get("fields", {})
        if fields.get("对战ID") == battle_id and fields.get("玩家侧") == side:
            cid = fields.get("卡牌ID", "")
            cards.append({
                "card_id": cid,
                "name": fields.get("卡牌名称", ""),
                "category": fields.get("类别", ""),
                "aspect": fields.get("性相", ""),
                "level_requirement": 0,
                "effect_text": "",
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

    # 3. 写入 Base（牌位1-8 + 牌库已确认）
    await base_sync.sync_deck_confirmed(battle_id, side, card_ids)

    # 4. 检查对手是否已确认
    both_ready = await base_sync.check_both_decks_confirmed(battle_id)

    if both_ready:
        # 5. 从 Base 读取双方牌库
        my_record = await _get_player_state_record(battle_id, side)
        opp_record = await _get_player_state_record(battle_id, _other_side(side))
        a_deck = _read_deck_slots(my_record) if side == "A" else _read_deck_slots(opp_record)
        b_deck = _read_deck_slots(opp_record) if side == "A" else _read_deck_slots(my_record)

        if len(a_deck) != 8 or len(b_deck) != 8:
            return {"ok": False, "status": "error",
                    "message": f"牌库不完整 A:{len(a_deck)} B:{len(b_deck)}"}

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
    if result.status == "resolved" and result.result:
        r = result.result
        return {
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
    return {
        "ok": True, "status": result.status,
        "round": result.round, "message": result.message,
    }


# ════════════════════════════════════════════════════
# 战斗日志（玩家视角）
# ════════════════════════════════════════════════════

async def get_battle_logs(name: str) -> dict:
    """获取玩家视角的战斗日志"""
    battle = await _find_player_battle(name)
    if not battle:
        return {"ok": False, "message": f"玩家 {name} 没有进行中的战斗"}
    battle_id = battle["fields"].get("对战ID", "")
    side = battle["fields"].get("玩家侧", "")

    records = await feishu_client.list_records(BASE_TOKEN, TABLE_BATTLE_LOG)
    logs = []
    for r in records:
        fields = r.get("fields", {})
        if fields.get("对战ID") == battle_id:
            logs.append({
                "round": _int_field(r, "回合编号", 0),
                "my_card": fields.get("A使用卡牌" if side == "A" else "B使用卡牌", ""),
                "opponent_card": fields.get("B使用卡牌" if side == "A" else "A使用卡牌", ""),
                "rps_description": fields.get("RPS结果描述", ""),
                "damage_to_me": _int_field(r, "A受到伤害" if side == "A" else "B受到伤害", 0),
                "damage_to_opponent": _int_field(r, "B受到伤害" if side == "A" else "A受到伤害", 0),
                "my_hp_after": _int_field(r, "A剩余HP" if side == "A" else "B剩余HP", 20),
                "opponent_hp_after": _int_field(r, "B剩余HP" if side == "A" else "A剩余HP", 20),
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


async def _get_battle_state(battle_id: str) -> str:
    record = await _get_battle_record(battle_id)
    if record is None:
        return ""
    return record.get("fields", {}).get("状态", "")


async def _get_battle_record(battle_id: str) -> Optional[dict]:
    """从对战管理表查一条记录"""
    records = await feishu_client.list_records(BASE_TOKEN, TABLE_BATTLE)
    for r in records:
        if r.get("fields", {}).get("对战ID") == battle_id:
            return r
    return None


async def _get_player_state_record(battle_id: str, side: str) -> Optional[dict]:
    """从玩家战斗状态表查指定对战+侧的一条记录"""
    records = await feishu_client.list_records(BASE_TOKEN, TABLE_PLAYER_STATE)
    for r in records:
        fields = r.get("fields", {})
        if fields.get("对战ID") == battle_id and fields.get("玩家侧") == side:
            return r
    return None


async def _find_player_battle(name: str) -> Optional[dict]:
    """在玩家战斗状态表中查找玩家当前活跃的战斗（优先非结束状态）"""
    records = await feishu_client.list_records(BASE_TOKEN, TABLE_PLAYER_STATE)
    for r in records:
        if r.get("fields", {}).get("玩家名称") == name:
            # 检查对应对战是否已结束
            bid = r["fields"].get("对战ID", "")
            battle = await _get_battle_record(bid)
            if battle and battle["fields"].get("状态", "") not in ("已结束", ""):
                return r
    # 兜底：如果没有活跃对战，返回最近一条（已结束也能查看）
    for r in records:
        if r.get("fields", {}).get("玩家名称") == name:
            return r
    return None


async def _get_available_card_ids(battle_id: str, side: str) -> List[str]:
    """获取指定对战+侧的全部可用卡牌ID"""
    records = await feishu_client.list_records(BASE_TOKEN, TABLE_AVAILABLE)
    return [r["fields"].get("卡牌ID", "")
            for r in records
            if (r.get("fields", {}).get("对战ID") == battle_id
                and r.get("fields", {}).get("玩家侧") == side)]


async def _has_submitted_this_round(battle_id: str, side: str,
                                    current_round: int, battle_manager=None) -> bool:
    """检查指定侧在当前回合是否已提交 — 优先读 BattleManager 内存，回退 Base"""
    if current_round == 0:
        return False

    # 优先查 BattleManager 内存（即时，无 Base 异步写入延迟）
    if battle_manager is not None:
        session = battle_manager._battles.get(battle_id)
        if session is not None:
            sub = session.submission_a if side.upper() == "A" else session.submission_b
            return sub is not None

    # Base 回退（服务重启后 session 丢失时）
    records = await feishu_client.list_records(BASE_TOKEN, TABLE_SUBMISSION)
    for r in records:
        fields = r.get("fields", {})
        if (fields.get("对战ID") == battle_id
                and fields.get("玩家侧") == side
                and _int_field(r, "回合编号", 0) == current_round):
            return True
    return False
