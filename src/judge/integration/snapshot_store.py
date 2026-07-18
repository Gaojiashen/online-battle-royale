"""
SnapshotStore — 战斗快照持久化。

将 BattleSession 的关键状态序列化为 JSON 文件。
用于崩溃恢复时快速重建内存状态。

存储: data/snapshots/{battle_id}.json
"""

import os
import json
import logging
from typing import Dict, Any, List, Optional
from dataclasses import asdict

from engine.battle_manager import BattleSession
from engine.resource_engine import BattleState
from engine.card_library import CARDS_BY_ID

logger = logging.getLogger(__name__)


class SnapshotStore:
    """
    战斗快照存储。

    文件格式: JSON
    每个 battle 一个文件: data/snapshots/{battle_id}.json
    """

    def __init__(self, data_dir: str = "data/snapshots"):
        self._data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    # ════════════════════════════════════════════════════
    # 公共接口
    # ════════════════════════════════════════════════════

    def save(self, session: BattleSession, last_event_id: str = "") -> None:
        """
        保存 BattleSession 快照。

        异常不抛出，记录 CRITICAL 日志。
        """
        filepath = self._filepath(session.id)
        try:
            snapshot = {
                "battle_id": session.id,
                "last_event_id": last_event_id,
                "player_a_name": session.player_a_name,
                "player_b_name": session.player_b_name,
                "player_a_base_token": session.player_a_base_token,
                "player_b_base_token": session.player_b_base_token,
                "player_a_aspects": session.player_a_aspects,
                "player_b_aspects": session.player_b_aspects,
                "player_a_available": session.player_a_available,
                "player_b_available": session.player_b_available,
                "player_a_deck": session.player_a_deck,
                "player_b_deck": session.player_b_deck,
                "state_a": self._serialize_battle_state(session.state_a),
                "state_b": self._serialize_battle_state(session.state_b),
                "current_round": session.current_round,
                "battle_state": session.state,
                "submission_a": session.submission_a,
                "submission_b": session.submission_b,
                "rounds_count": len(session.rounds),
                "winner": session.winner,
                "end_reason": session.end_reason,
            }
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            logger.info(f"Snapshot saved: {session.id} r={session.current_round}")
        except Exception:
            logger.critical(
                f"Snapshot save failed: {session.id}", exc_info=True
            )

    def load(self, battle_id: str) -> Optional[Dict[str, Any]]:
        """
        加载 BattleSession 快照。

        文件不存在或解析失败返回 None。
        """
        filepath = self._filepath(battle_id)
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            logger.warning(
                f"Snapshot load failed: {battle_id}", exc_info=True
            )
            return None

    def list_active_snapshots(self) -> List[str]:
        """
        列出所有快照文件对应的 battle_id。

        只返回 battle_state 不是 "finished" 的快照。
        用于启动恢复时找到所有未结束对战。
        """
        active = []
        if not os.path.isdir(self._data_dir):
            return active

        for fname in os.listdir(self._data_dir):
            if not fname.endswith(".json"):
                continue
            battle_id = fname[:-5]  # 去掉 .json 后缀
            snapshot = self.load(battle_id)
            if snapshot and snapshot.get("battle_state") != "finished":
                active.append(battle_id)
        return active

    def delete(self, battle_id: str) -> None:
        """删除指定对战的快照文件"""
        filepath = self._filepath(battle_id)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except OSError:
            logger.warning(f"Snapshot delete failed: {battle_id}", exc_info=True)

    # ════════════════════════════════════════════════════
    # 内部
    # ════════════════════════════════════════════════════

    def _filepath(self, battle_id: str) -> str:
        return os.path.join(self._data_dir, f"{battle_id}.json")

    @staticmethod
    def _serialize_battle_state(bs: Optional[BattleState]) -> Optional[Dict[str, Any]]:
        """序列化 BattleState 为 dict"""
        if bs is None:
            return None
        return {
            "hp": bs.hp,
            "max_hp": bs.max_hp,
            "edge": bs.edge,
            "phantom": bs.phantom,
            "charge": bs.charge,
            "self_chill": bs.self_chill,
            "pulse": bs.pulse,
            "read": bs.read,
            "insight": bs.insight,
            "blade_level": bs.blade_level,
            "moth_level": bs.moth_level,
            "forge_level": bs.forge_level,
            "winter_level": bs.winter_level,
            "heart_level": bs.heart_level,
            "lantern_level": bs.lantern_level,
        }
